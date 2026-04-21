"""WebSocket endpoints for live container stats.

Streams CPU, memory, and network deltas for every running container
at `config.stats_interval` intervals. Clients subscribe to a single
endpoint and receive periodic snapshots.

Performance note: Docker's stats(stream=False) takes ~1-2s per container
because it needs a full CPU sampling window to calculate deltas. We run
all containers concurrently in a thread pool so 10 containers take ~2s
total instead of 10-20s sequential. The interval timer starts AFTER
collection completes so the UI always gets fresh data without stacking.
"""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from . import docker_client
from .config import config

logger = logging.getLogger(__name__)

# Thread pool sized to the typical number of containers. Each worker
# blocks on one Docker stats call — we want enough workers to run all
# containers concurrently without thrashing.
_stats_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="stats")


def _fetch_one(container) -> dict | None:
    """Fetch stats for a single container (blocking). Runs in thread pool."""
    try:
        raw = container.stats(stream=False)
        parsed = docker_client._parse_stats(container.name, container.id, raw)
        return parsed.model_dump()
    except Exception as e:
        logger.debug("Stats fetch failed for %s: %s", container.name, e)
        return None


class StatsHub:
    """Singleton that polls Docker stats and fans out to all WS clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("Stats client connected (%d total)", len(self._clients))
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._broadcast_loop())

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("Stats client disconnected (%d left)", len(self._clients))

    async def _broadcast_loop(self) -> None:
        """Poll and broadcast at a fixed interval until no clients remain."""
        while self._clients:
            try:
                snapshot = await self._collect_all()
                if self._clients:  # recheck after await
                    await self._broadcast(json.dumps(snapshot))
            except Exception:
                logger.exception("Stats broadcast error")
            # Wait between samples. Using sleep AFTER collection means
            # the interval is "every N seconds after data arrives" not
            # "every N seconds regardless of how long collection took".
            await asyncio.sleep(config.stats_interval)
        logger.info("No stats clients remain — loop exiting")
        self._task = None

    async def _collect_all(self) -> dict[str, Any]:
        """Fetch stats for all running containers concurrently.

        Each container's stats call blocks for ~1-2s in Docker's sampling
        window. Running them all in parallel via the thread pool means
        wall-clock time is ~2s regardless of container count.
        """
        loop = asyncio.get_running_loop()
        try:
            containers = docker_client.client().containers.list()
        except Exception as e:
            logger.warning("Could not list containers for stats: %s", e)
            return {"type": "stats", "containers": []}

        # Submit all stats calls concurrently
        futures = [
            loop.run_in_executor(_stats_executor, _fetch_one, c)
            for c in containers
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)

        rows = [r for r in results if isinstance(r, dict)]
        return {"type": "stats", "containers": rows}

    async def _broadcast(self, payload: str) -> None:
        """Send payload to every connected client, dropping dead ones."""
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = StatsHub()


async def stats_endpoint(ws: WebSocket) -> None:
    """FastAPI WebSocket handler."""
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)


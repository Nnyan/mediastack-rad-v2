"""WebSocket endpoints for live container stats.

Streams CPU, memory, and network deltas for every running container
at `config.stats_interval` intervals. Clients subscribe to a single
endpoint and receive periodic snapshots — no per-container connections.

The background task fans out to all connected sockets. If any client
falls behind, the send errors out and we drop that connection rather
than blocking the broadcast loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from . import docker_client
from .config import config

logger = logging.getLogger(__name__)


class StatsHub:
    """Singleton that polls Docker stats and fans out to all WS clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("Stats client connected (%d total)", len(self._clients))
        # Start the broadcast loop on first connection.
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._broadcast_loop())

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("Stats client disconnected (%d left)", len(self._clients))

    async def _broadcast_loop(self) -> None:
        """Poll and send at a fixed interval until no clients remain."""
        while self._clients:
            try:
                snapshot = self._collect()
                payload = json.dumps(snapshot)
                await self._broadcast(payload)
            except Exception:  # noqa: BLE001
                logger.exception("Stats broadcast error")
            await asyncio.sleep(config.stats_interval)
        logger.info("No stats clients remain; loop exiting")
        self._task = None

    def _collect(self) -> dict[str, Any]:
        """Gather a single snapshot of stats for all running containers.

        We use the non-streaming `stats(stream=False)` call which is
        cheaper than maintaining a stream per container — at our
        interval (2s) the difference is negligible and the code stays
        much simpler.
        """
        rows = []
        for c in docker_client.client().containers.list():
            try:
                raw = c.stats(stream=False)
                parsed = docker_client._parse_stats(c.name, c.id, raw)
                rows.append(parsed.model_dump())
            except Exception as e:  # noqa: BLE001
                logger.debug("Stats fetch failed for %s: %s", c.name, e)
        return {"type": "stats", "containers": rows}

    async def _broadcast(self, payload: str) -> None:
        """Send a payload to every client, dropping those that error."""
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = StatsHub()


async def stats_endpoint(ws: WebSocket) -> None:
    """FastAPI-style WebSocket handler wired up in main.py."""
    await hub.connect(ws)
    try:
        # Keep the connection open until the client disconnects.
        # We don't expect messages from the client yet, but we still
        # need to receive to detect disconnection.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)

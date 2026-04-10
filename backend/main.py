"""
MediaStack-RAD v2 — Backend
FastAPI + docker-py: real container management via Docker socket.
"""

import asyncio
import json
import logging
from typing import Any

import docker
import docker.errors
from docker.models.containers import Container
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mediastack-rad")

app = FastAPI(title="MediaStack-RAD", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Docker client ─────────────────────────────────────────────────────────────

def get_docker() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
        return client
    except docker.errors.DockerException as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Docker socket: {e}. "
                   "Ensure /var/run/docker.sock is mounted.",
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_image_name(container: Container) -> str:
    try:
        tags = container.image.tags
        return tags[0] if tags else container.attrs["Config"]["Image"]
    except Exception:
        return "unknown"


def _container_summary(container: Container) -> dict[str, Any]:
    attrs = container.attrs or {}
    config = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})
    network_settings = attrs.get("NetworkSettings", {})

    ports: dict[str, Any] = {}
    bindings = network_settings.get("Ports") or {}
    for container_port, host_bindings in bindings.items():
        if host_bindings:
            ports[container_port] = [b["HostPort"] for b in host_bindings]

    return {
        "id": container.short_id,
        "name": container.name,
        "status": container.status,
        "image": _safe_image_name(container),
        "ports": ports,
        "restart_policy": host_config.get("RestartPolicy", {}).get("Name", "no"),
        "created": attrs.get("Created", ""),
        "labels": config.get("Labels") or {},
        "networks": list((network_settings.get("Networks") or {}).keys()),
    }


def _container_stats_once(container: Container) -> dict[str, Any]:
    """Pull one stats sample (non-streaming) and compute CPU + memory."""
    try:
        raw = container.stats(stream=False)
    except Exception:
        return {"cpu_percent": 0.0, "memory_mb": 0.0, "memory_limit_mb": 0.0}

    # CPU %
    cpu_delta = (
        raw["cpu_stats"]["cpu_usage"]["total_usage"]
        - raw["precpu_stats"]["cpu_usage"]["total_usage"]
    )
    system_delta = (
        raw["cpu_stats"].get("system_cpu_usage", 0)
        - raw["precpu_stats"].get("system_cpu_usage", 0)
    )
    num_cpus = raw["cpu_stats"].get("online_cpus") or len(
        raw["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])
    )
    cpu_pct = (cpu_delta / system_delta * num_cpus * 100.0) if system_delta > 0 else 0.0

    # Memory
    mem = raw.get("memory_stats", {})
    usage = mem.get("usage", 0) - mem.get("stats", {}).get("cache", 0)
    limit = mem.get("limit", 0)

    return {
        "cpu_percent": round(cpu_pct, 2),
        "memory_mb": round(usage / 1024 / 1024, 1),
        "memory_limit_mb": round(limit / 1024 / 1024, 1),
    }


# ── REST API ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/docker/info")
def docker_info():
    client = get_docker()
    info = client.info()
    return {
        "docker_version": client.version()["Version"],
        "containers_running": info["ContainersRunning"],
        "containers_stopped": info["ContainersStopped"],
        "containers_paused": info["ContainersPaused"],
        "images": info["Images"],
        "server_version": info["ServerVersion"],
        "os": info["OperatingSystem"],
        "architecture": info["Architecture"],
        "cpus": info["NCPU"],
        "memory_gb": round(info["MemTotal"] / 1024 / 1024 / 1024, 1),
    }


@app.get("/api/containers")
def list_containers(all: bool = True):
    client = get_docker()
    containers = client.containers.list(all=all)
    return [_container_summary(c) for c in containers]


@app.get("/api/containers/{container_id}")
def get_container(container_id: str):
    client = get_docker()
    try:
        container = client.containers.get(container_id)
        summary = _container_summary(container)
        if container.status == "running":
            summary.update(_container_stats_once(container))
        return summary
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{container_id}' not found")


@app.post("/api/containers/{container_id}/start")
def start_container(container_id: str):
    client = get_docker()
    try:
        container = client.containers.get(container_id)
        container.start()
        log.info("Started container: %s", container.name)
        return {"ok": True, "name": container.name, "status": "running"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{container_id}' not found")
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/containers/{container_id}/stop")
def stop_container(container_id: str):
    client = get_docker()
    try:
        container = client.containers.get(container_id)
        container.stop(timeout=10)
        log.info("Stopped container: %s", container.name)
        return {"ok": True, "name": container.name, "status": "exited"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{container_id}' not found")
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/containers/{container_id}/restart")
def restart_container(container_id: str):
    client = get_docker()
    try:
        container = client.containers.get(container_id)
        container.restart(timeout=10)
        log.info("Restarted container: %s", container.name)
        return {"ok": True, "name": container.name, "status": "running"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{container_id}' not found")
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/containers/{container_id}/logs")
def get_logs(container_id: str, tail: int = 100):
    client = get_docker()
    try:
        container = client.containers.get(container_id)
        raw = container.logs(tail=tail, timestamps=True)
        lines = raw.decode("utf-8", errors="replace").strip().splitlines()
        return {"lines": lines}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{container_id}' not found")


@app.get("/api/containers/{container_id}/stats")
def get_stats(container_id: str):
    client = get_docker()
    try:
        container = client.containers.get(container_id)
        if container.status != "running":
            return {"cpu_percent": 0.0, "memory_mb": 0.0, "memory_limit_mb": 0.0}
        return _container_stats_once(container)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{container_id}' not found")


@app.get("/api/networks")
def list_networks():
    client = get_docker()
    networks = client.networks.list()
    return [
        {
            "id": n.short_id,
            "name": n.name,
            "driver": n.attrs.get("Driver", ""),
            "scope": n.attrs.get("Scope", ""),
            "containers": len(n.attrs.get("Containers") or {}),
        }
        for n in networks
    ]


@app.get("/api/images")
def list_images():
    client = get_docker()
    images = client.images.list()
    result = []
    for img in images:
        size_mb = round(img.attrs.get("Size", 0) / 1024 / 1024, 1)
        result.append({
            "id": img.short_id.replace("sha256:", ""),
            "tags": img.tags,
            "size_mb": size_mb,
            "created": img.attrs.get("Created", ""),
        })
    return result


# ── WebSocket: live stats stream ──────────────────────────────────────────────

@app.websocket("/ws/stats")
async def stats_stream(websocket: WebSocket):
    """
    Streams CPU + memory stats for all running containers every 2 seconds.
    Client receives: { "container_id": { cpu_percent, memory_mb, memory_limit_mb } }
    """
    await websocket.accept()
    log.info("WebSocket stats client connected")
    try:
        while True:
            try:
                client = get_docker()
                running = client.containers.list()
            except HTTPException:
                await websocket.send_text(json.dumps({"error": "Docker unavailable"}))
                await asyncio.sleep(5)
                continue

            payload: dict[str, Any] = {}
            for container in running:
                loop = asyncio.get_event_loop()
                stats = await loop.run_in_executor(None, _container_stats_once, container)
                payload[container.short_id] = stats

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        log.info("WebSocket stats client disconnected")


# ── Serve Vue frontend (production) ──────────────────────────────────────────

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(_full_path: str = ""):
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")

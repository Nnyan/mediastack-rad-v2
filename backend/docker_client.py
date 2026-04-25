"""Thin wrapper around docker-py that adds retry, logging, and the
specific helpers we use across the app.

We intentionally do not expose the docker-py client directly to the
rest of the code — every Docker interaction goes through this module
so permissions, error handling, and testing are centralized.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Iterator

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

from .config import config
from .models import ContainerPort, ContainerStats, ContainerSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------


_client: docker.DockerClient | None = None


def client() -> docker.DockerClient:
    """Return the shared Docker client, creating it on first access.

    Resets the cached client if the daemon has restarted — if the
    existing client raises DockerException we clear it so the next
    call gets a fresh connection instead of retrying against the same
    broken socket.
    """
    global _client
    if _client is None:
        logger.info("Connecting to Docker at %s", config.docker_socket)
        try:
            _client = docker.DockerClient(base_url=config.docker_socket)
        except DockerException:
            _client = None
            raise
    return _client


def _reset_client() -> None:
    """Clear the cached client so the next call reconnects.

    Called when a DockerException suggests the daemon restarted.
    """
    global _client
    _client = None


def ping() -> bool:
    """Quick liveness check — returns True if the daemon responds.

    Resets the cached client on failure so the next call reconnects.
    """
    try:
        result = client().ping()
        return bool(result)
    except (DockerException, OSError):
        _reset_client()
        return False


def with_retry(fn, *, attempts: int = 3, backoff: float = 0.5):
    """Retry a Docker call on transient failure.

    Some operations (recreate, network connect) race with each other
    during a full stack redeploy and need a few retries. We catch the
    broad APIError + DockerException rather than sniffing error codes
    because the Docker daemon's error messages aren't stable across
    versions.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except (APIError, DockerException) as e:
            last_exc = e
            if attempt == attempts:
                break
            logger.warning(
                "Docker call failed (attempt %d/%d): %s — retrying in %ss",
                attempt, attempts, e, backoff,
            )
            # Reset the client so the retry gets a fresh connection.
            # If the daemon restarted, reusing the same broken socket
            # guarantees all retries fail.
            _reset_client()
            time.sleep(backoff * attempt)
    raise last_exc  # type: ignore[misc]


async def with_retry_async(fn, attempts: int = 3, backoff: float = 1.0):
    return await asyncio.to_thread(with_retry, fn, attempts=attempts, backoff=backoff)


# ---------------------------------------------------------------------------
# Container queries
# ---------------------------------------------------------------------------


def list_containers(include_stopped: bool = True) -> list[ContainerSummary]:
    """Return every container on the host as a summary dict."""
    raw = client().containers.list(all=include_stopped)
    return [_summarize(c) for c in raw]


def get_container(name_or_id: str) -> Container:
    """Fetch a container by name or ID; raises NotFound if missing."""
    return client().containers.get(name_or_id)


def get_container_safe(name_or_id: str) -> Container | None:
    """Same as get_container but returns None instead of raising."""
    try:
        return client().containers.get(name_or_id)
    except NotFound:
        return None


def _summarize(c: Container) -> ContainerSummary:
    """Convert a docker-py Container to our API schema."""
    attrs = c.attrs or {}
    state = attrs.get("State") or {}
    net = attrs.get("NetworkSettings") or {}
    cfg = attrs.get("Config") or {}
    host_cfg = attrs.get("HostConfig") or {}

    # Parse port bindings. Docker returns a mapping like:
    #   {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"},
    #                 {"HostIp": "::",       "HostPort": "8080"}], ...}
    # Docker binds each port on both IPv4 (0.0.0.0) and IPv6 (::) interfaces,
    # producing duplicate entries. We deduplicate on (host_port, container_port,
    # protocol) — the HostIp doesn't matter for our display purposes.
    ports: list[ContainerPort] = []
    seen_ports: set[tuple] = set()
    bindings = net.get("Ports") or host_cfg.get("PortBindings") or {}
    for port_key, hosts in (bindings or {}).items():
        if "/" in port_key:
            cport_s, proto = port_key.split("/", 1)
        else:
            cport_s, proto = port_key, "tcp"
        try:
            cport = int(cport_s)
        except ValueError:
            continue
        proto = proto if proto in ("tcp", "udp") else "tcp"
        if hosts:
            for h in hosts:
                try:
                    hp = int(h.get("HostPort") or 0) or None
                except (TypeError, ValueError):
                    hp = None
                key = (hp, cport, proto)
                if key in seen_ports:
                    continue
                seen_ports.add(key)
                ports.append(ContainerPort(
                    host_port=hp,
                    container_port=cport,
                    protocol=proto,
                ))
        else:
            key = (None, cport, proto)
            if key not in seen_ports:
                seen_ports.add(key)
                ports.append(ContainerPort(
                    container_port=cport,
                    protocol=proto,
                ))

    # Networks as a simple name list
    networks = list((net.get("Networks") or {}).keys())

    # Parse created timestamp (Docker returns ISO 8601 string)
    created_s = attrs.get("Created", "")
    created = _iso_to_unix(created_s)

    # Extract Docker healthcheck state if present
    # State.Health.Status: healthy | unhealthy | starting | none
    health_info = state.get("Health") or {}
    health = health_info.get("Status") or "none"

    # Determine best web URL from Traefik labels or host port
    web_url = _web_url(labels=cfg.get("Labels") or {}, ports=ports, name=c.name)

    return ContainerSummary(
        id=c.id[:12],
        name=c.name,
        image=(cfg.get("Image") or ""),
        status=c.status,
        state=state.get("Status", "unknown"),
        health=health,
        created=created,
        ports=ports,
        labels=cfg.get("Labels") or {},
        networks=networks,
        web_url=web_url,
    )


_KNOWN_WEB_PORTS = {
    80, 443, 3000, 5055, 5000, 6767, 6789, 7878, 8080, 8081,
    8085, 8096, 8686, 8787, 8989, 9696, 32400,
}

_SPECIAL_PATHS = {
    "plex": "/web",
    "traefik": "/dashboard/",
}


def _web_url(labels: dict, ports: list[ContainerPort], name: str) -> str | None:
    """Return the best URL for a container's web UI.

    Prefer the direct LAN URL (host:port). Traefik labels are only used when the
    service exposes no host port.
    """
    import re
    if name == "traefik":
        port = next((p for p in ports if p.host_port and p.container_port == 8081), None)
        if port:
            return f"http://0.0.0.0:{port.host_port}/dashboard/"
        # If 8081 isn't mapped, fall back to router host (rare)
        for key, val in labels.items():
            if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
                m = re.search(r"Host\(`([^`]+)`\)", val)
                if m:
                    return f"https://{m.group(1)}/dashboard/"
        return None

    port = next((p for p in ports if p.host_port and p.container_port in _KNOWN_WEB_PORTS), None)
    if port:
        scheme = "https" if port.container_port == 443 else "http"
        path = _SPECIAL_PATHS.get(name, "")
        return f"{scheme}://0.0.0.0:{port.host_port}{path}"

    for key, val in labels.items():
        if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
            m = re.search(r"Host\(`([^`]+)`\)", val)
            if m:
                host = m.group(1)
                if not host.startswith("auth."):
                    return f"https://{host}/"
    return None


def _iso_to_unix(iso: str) -> int:
    """Parse Docker's ISO timestamp to a Unix int. Returns 0 on failure."""
    try:
        # Docker strings look like "2024-01-15T12:34:56.789Z" — strip sub-seconds.
        if "." in iso:
            iso = iso.split(".", 1)[0] + "Z"
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Container operations
# ---------------------------------------------------------------------------


def start(name: str) -> None:
    """Start a stopped container."""
    with_retry(lambda: get_container(name).start())


def stop(name: str, timeout: int = 10) -> None:
    """Stop a running container; SIGKILL after `timeout` seconds."""
    with_retry(lambda: get_container(name).stop(timeout=timeout))


def restart(name: str, timeout: int = 10) -> None:
    """Restart a container in-place (same config)."""
    with_retry(lambda: get_container(name).restart(timeout=timeout))


def remove(name: str, force: bool = False) -> None:
    """Remove a container. force=True also stops running ones."""
    c = get_container_safe(name)
    if c is None:
        return
    with_retry(lambda: c.remove(force=force))


def remove_ghost_containers() -> list[str]:
    """Remove all stopped containers that share a name with a running one.

    This is the "ghost container" bug we hit repeatedly — after a failed
    recreate, Docker keeps a renamed copy (e.g. `76c5b821f40b_sabnzbd`)
    which blocks future compose operations for that service.
    """
    removed = []
    for c in client().containers.list(all=True):
        # Ghost naming pattern: 12-char hex + underscore + service name.
        # We could match the regex, but simpler: ghosts are stopped and
        # their name contains an underscore that real compose services
        # wouldn't have.
        if c.status not in ("running", "restarting", "paused"):
            if "_" in c.name and len(c.name.split("_", 1)[0]) == 12:
                try:
                    c.remove(force=True)
                    removed.append(c.name)
                    logger.info("Removed ghost container %s", c.name)
                except APIError as e:
                    logger.warning("Failed to remove ghost %s: %s", c.name, e)
    return removed


# ---------------------------------------------------------------------------
# Stats streaming
# ---------------------------------------------------------------------------


def stats_stream(container_id: str) -> Iterator[ContainerStats]:
    """Yield ContainerStats objects from a live Docker stats stream.

    The caller is responsible for terminating the loop — a WebSocket
    handler typically stops by breaking out of `async for`.
    """
    c = get_container(container_id)
    for raw in c.stats(stream=True, decode=True):
        yield _parse_stats(c.name, container_id, raw)


def _parse_stats(name: str, cid: str, raw: dict) -> ContainerStats:
    """Parse Docker's stats JSON into our schema."""
    # CPU: derived from cumulative usage diff since previous sample.
    cpu_stats = raw.get("cpu_stats", {})
    pre_stats = raw.get("precpu_stats", {})
    cpu_delta = (cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                 - pre_stats.get("cpu_usage", {}).get("total_usage", 0))
    sys_delta = (cpu_stats.get("system_cpu_usage", 0)
                 - pre_stats.get("system_cpu_usage", 0))
    ncpus = cpu_stats.get("online_cpus") or len(
        cpu_stats.get("cpu_usage", {}).get("percpu_usage") or []
    ) or 1
    cpu_pct = 0.0
    if cpu_delta > 0 and sys_delta > 0:
        cpu_pct = (cpu_delta / sys_delta) * ncpus * 100.0

    # Memory
    mem = raw.get("memory_stats", {})
    mem_usage = mem.get("usage", 0) - (mem.get("stats", {}).get("cache") or 0)
    mem_limit = mem.get("limit", 0) or 1
    mem_pct = (mem_usage / mem_limit) * 100.0 if mem_limit else 0.0

    # Network (sum across all interfaces)
    nets = raw.get("networks") or {}
    rx = sum(n.get("rx_bytes", 0) for n in nets.values())
    tx = sum(n.get("tx_bytes", 0) for n in nets.values())

    return ContainerStats(
        id=cid[:12],
        name=name,
        cpu_percent=round(cpu_pct, 2),
        mem_usage_bytes=int(mem_usage),
        mem_limit_bytes=int(mem_limit),
        mem_percent=round(mem_pct, 2),
        net_rx_bytes=int(rx),
        net_tx_bytes=int(tx),
    )


# ---------------------------------------------------------------------------
# Host info
# ---------------------------------------------------------------------------


def daemon_info() -> dict:
    """Return Docker daemon version and capacity info for the header bar."""
    try:
        info = client().info()
        version = client().version()
        return {
            "docker_version": version.get("Version", "unknown"),
            "api_version": version.get("ApiVersion", "unknown"),
            "running": info.get("ContainersRunning", 0),
            "stopped": info.get("ContainersStopped", 0),
            "paused": info.get("ContainersPaused", 0),
            "cpus": info.get("NCPU", 0),
            "memory_bytes": info.get("MemTotal", 0),
        }
    except (DockerException, OSError) as e:
        logger.error("Cannot get daemon info: %s", e)
        _reset_client()
        return {"error": str(e)}

"""FastAPI application for MediaStack-RAD.

IMPORTANT — SPA route ordering:
================================
The SPA catch-all route (/{full_path:path}) MUST be registered as the
very last route. If it comes before an API route, every API call gets
served the index.html file silently and debugging is miserable.

To prevent regression, we use the `_verify_route_order` function at
startup which asserts that no API routes appear after the catch-all.
The app refuses to start if ordering is wrong.

This is exactly the bug that made our original v2 return HTML for
/api/containers calls — fixed here by construction AND verified on
each boot.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import os
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import catalog as catalog_mod
from . import checklist as checklist_mod
from . import docker_client
from . import generator as generator_mod
from .models import SecretEntry, SecretValue, StackValidation
from . import health as health_mod
from . import websocket as ws_mod
from .config import config
from .models import (
    ChecklistItem,
    ContainerSummary,
    HealthReport,
    StackRequest,
)

# Set up logging early so startup messages are captured.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
logger = logging.getLogger("rad")


def _compose_up_timeout_seconds() -> int:
    """Maximum seconds to wait for `docker compose up -d` to finish."""

    raw = os.environ.get("RAD_COMPOSE_UP_TIMEOUT", "600")
    try:
        return max(30, int(raw))
    except ValueError:
        logger.warning(
            "Invalid RAD_COMPOSE_UP_TIMEOUT=%s. Falling back to 600s.",
            raw,
        )
        return 600


COMPOSE_UP_TIMEOUT_SECONDS = _compose_up_timeout_seconds()
ROUTE_CHECK_ATTEMPTS = 15
ROUTE_CHECK_BASE_DELAY_SECONDS = 1.0


def _can_write_directory(path: Path) -> bool:
    probe = path / f".rad-meta-probe-{os.getpid()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _build_docker_env() -> dict[str, str]:
    """Prepare a stable environment for docker CLI invocations inside RAD."""

    env = os.environ.copy()
    # Avoid noisy/permission-denied reads from /root/.docker when running as
    # a non-root container user with HOME=/root.
    home = env.get("HOME")
    if not home or home.startswith("/root"):
        home = tempfile.gettempdir()
        env["HOME"] = home
    env["DOCKER_CONFIG"] = f"{home}/.docker"
    return env


def _compose_not_supported(stderr: str) -> bool:
    """Detect CLI outputs that indicate docker-compose command is unavailable."""

    text = stderr.lower()
    return (
        "'compose' is not a docker command" in text
        or "unknown shorthand flag: '-f'" in text
        or "unknown shorthand flag: \"-f\"" in text
        or "unknown command: compose" in text
        or "unknown command \"compose\"" in text
    )


async def _run_docker_compose_up(path: Path) -> tuple[str, int, str, str]:
    """Run docker-compose up using v2 or legacy v1 syntax.

    Returns (command_label, returncode, stdout, stderr).
    """
    env = _build_docker_env()
    argv_list = [
        ("docker compose", ["docker", "compose", "-f", str(path), "up", "-d"]),
        ("docker-compose", ["docker-compose", "-f", str(path), "up", "-d"]),
    ]

    last_error = None
    for i, (command_label, argv) in enumerate(argv_list):
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=COMPOSE_UP_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise HTTPException(
                    504,
                    f"docker compose up timed out after {COMPOSE_UP_TIMEOUT_SECONDS}s. "
                    "Large image pulls or slow disks are common causes. "
                    "Increase RAD_COMPOSE_UP_TIMEOUT if needed.",
                )

            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                return command_label, proc.returncode, stdout, stderr

            if i < len(argv_list) - 1 and _compose_not_supported(stderr):
                last_error = stderr
                continue

            return command_label, proc.returncode, stdout, stderr

        except FileNotFoundError:
            if i < len(argv_list) - 1:
                last_error = f"{command_label} not found"
                continue
            raise

    if last_error is None:
        last_error = "docker compose command failed"
    return "docker-compose", 1, "", last_error


# ---------------------------------------------------------------------------
# Lifespan — start and stop the health checker loop cleanly
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Context manager that runs at startup and shutdown.

    We intentionally don't fail startup if Docker is unreachable —
    the dashboard should still load so the user can see *why* it's
    broken. The health report will surface the issue.
    """
    logger.info("MediaStack-RAD v%s starting", __version__)
    logger.info("Stack dir: %s", config.stack_dir)
    logger.info("Traefik dir: %s", config.traefik_dir)
    compose_path = config.stack_dir / "docker-compose.yml"
    logger.info("Compose path: %s", compose_path)
    if not _can_write_directory(config.stack_dir):
        logger.warning(
            "Stack directory is not writable by RAD: %s. Check mount permissions and owner/group, "
            "then restart after correcting the host path permissions.",
            config.stack_dir,
        )

    # Auto-connect to the managed stack network so container-to-container
    # calls (Traefik API proxy, Tinyauth) work without manual intervention.
    # This is necessary because Docker Compose silently skips external network
    # attachment when the network doesn't exist at RAD startup time.
    _auto_connect_network()

    # Kick off the health checker in the background.
    loop_task = asyncio.create_task(health_mod.cache.start_loop())

    try:
        yield
    finally:
        logger.info("MediaStack-RAD shutting down")
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass


def _auto_connect_network(network_name: str = "mediastack") -> None:
    """Ensure RAD is connected to the managed stack network.

    When the media stack hasn't been deployed yet the network won't exist
    and we log a warning. When the stack is up but RAD restarted first,
    the network exists but RAD isn't on it — we connect automatically.
    """
    try:
        d = docker_client.client()
        # Find this container's own ID from /proc/self/cgroup or hostname
        import socket
        hostname = socket.gethostname()  # Docker sets hostname = container ID prefix

        try:
            network = d.networks.get(network_name)
        except Exception:
            logger.warning(
                "Network '%s' does not exist yet — deploy the media stack first. "
                "RAD will reconnect on next restart.",
                network_name,
            )
            return

        # Find the RAD container by hostname match
        self_container = None
        for c in d.containers.list():
            if c.id.startswith(hostname) or c.attrs.get("Config", {}).get("Hostname") == hostname:
                self_container = c
                break

        if self_container is None:
            logger.debug("Could not locate own container for network auto-connect")
            return

        # Check if already connected
        connected = network.attrs.get("Containers", {})
        if self_container.id in connected:
            logger.info("Already connected to network '%s'", network_name)
            return

        network.connect(self_container.id)
        logger.info("Auto-connected to network '%s'", network_name)

    except Exception as e:
        logger.warning("Network auto-connect failed (non-fatal): %s", e)



app = FastAPI(
    title="MediaStack-RAD",
    version=__version__,
    description="Home media stack management dashboard",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Optional API key authentication
# ---------------------------------------------------------------------------

if config.api_key:

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        if request.url.path.startswith(("/api/", "/ws/")):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {config.api_key}":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    logger.info("API key authentication enabled")


@app.middleware("http")
async def ensure_json_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled API error at %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "message": "Internal server error",
                "detail": str(exc),
            },
        )


# ---------------------------------------------------------------------------
# API routes — ALL routes starting with /api/ must be declared here,
# BEFORE the SPA catch-all at the bottom of this file. See module
# docstring for why.
# ---------------------------------------------------------------------------


@app.get("/api/version")
async def api_version() -> dict:
    return {"version": __version__}


@app.get("/api/info")
async def api_info() -> dict:
    """Header bar info — Docker version, CPU/memory, container counts."""
    return docker_client.daemon_info()


# ---- Containers ------------------------------------------------------------


@app.get("/api/containers", response_model=list[ContainerSummary])
async def api_containers(all: bool = True) -> list[ContainerSummary]:
    return docker_client.list_containers(include_stopped=all)


@app.get("/api/containers/running")
async def api_running_containers() -> list[str]:
    """Return names of currently running containers for Stack Builder status."""
    return [c.name for c in docker_client.list_containers(include_stopped=False)]


@app.get("/api/containers/env")
async def api_containers_env(names: str = "") -> dict[str, dict[str, str]]:
    """Return environment variables for named containers.

    Query param `names` is a comma-separated list of container names.
    Returns { container_name: { KEY: VALUE, ... }, ... }.
    Values matching known secret patterns are masked.
    """
    MASK_KEYS = {
        "CF_DNS_API_TOKEN", "CLOUDFLARED_TOKEN", "TUNNEL_TOKEN",
        "TS_AUTHKEY", "TINYAUTH_AUTH_USERS", "PLEX_CLAIM", "PLEX_TOKEN",
        "OPENVPN_USER", "OPENVPN_PASSWORD", "WIREGUARD_PRIVATE_KEY",
    }
    result: dict[str, dict[str, str]] = {}
    if not names:
        return result
    for name in names.split(","):
        name = name.strip()
        if not name:
            continue
        c = docker_client.get_container_safe(name)
        if not c:
            continue
        env_map: dict[str, str] = {}
        for entry in (c.attrs.get("Config", {}).get("Env", []) or []):
            if "=" in entry:
                k, _, v = entry.partition("=")
                env_map[k] = "***" if k in MASK_KEYS else v
        result[name] = env_map
    return result


_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$')


def _validate_container_name(name: str) -> None:
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(400, f"Invalid container name: {name}")


@app.post("/api/containers/{name}/start")
async def api_start(name: str) -> dict:
    _validate_container_name(name)
    docker_client.start(name)
    return {"ok": True}


@app.post("/api/containers/{name}/stop")
async def api_stop(name: str) -> dict:
    _validate_container_name(name)
    docker_client.stop(name)
    return {"ok": True}


@app.post("/api/containers/{name}/restart")
async def api_restart(name: str) -> dict:
    _validate_container_name(name)
    docker_client.restart(name)
    return {"ok": True}


@app.delete("/api/containers/{name}")
async def api_remove(name: str, force: bool = True) -> dict:
    _validate_container_name(name)
    docker_client.remove(name, force=force)
    return {"ok": True}


@app.post("/api/containers/{name}/logs")
async def api_logs(name: str, tail: int = 200) -> PlainTextResponse:
    _validate_container_name(name)
    c = docker_client.get_container_safe(name)
    if c is None:
        raise HTTPException(404, f"No container named {name}")
    logs = c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
    return PlainTextResponse(logs)


@app.get("/api/vpn/status")
async def api_vpn_status() -> dict:
    """Return VPN ingress/egress status for the VPN dashboard."""
    tailscale = {"present": False, "status": "missing", "issues": []}
    c = docker_client.get_container_safe("tailscale")
    if c:
        env = {}
        for entry in (c.attrs.get("Config", {}).get("Env", []) or []):
            if "=" in entry:
                k, _, v = entry.partition("=")
                env[k] = "***" if k == "TS_AUTHKEY" else v
        host_cfg = c.attrs.get("HostConfig", {}) or {}
        cap_add = host_cfg.get("CapAdd") or []
        devices = host_cfg.get("Devices") or []
        has_tun = any("/dev/net/tun" in str(d.get("PathOnHost", "")) for d in devices)
        tailscale.update({
            "present": True,
            "status": c.status,
            "kernel_mode": env.get("TS_USERSPACE", "false").lower() == "false",
            "has_net_admin": "NET_ADMIN" in cap_add,
            "has_net_raw": "NET_RAW" in cap_add,
            "has_tun_device": has_tun,
            "hostname": env.get("TS_HOSTNAME", ""),
            "configured_routes": [r.strip() for r in env.get("TS_ROUTES", "").split(",") if r.strip()],
            "tailscale_ips": [],
            "backend_state": "unknown",
            "online": None,
            "peer_count": 0,
            "active_routes": [],
        })
        if c.status == "running":
            try:
                result = c.exec_run("tailscale status --json", demux=False)
                output = getattr(result, "output", b"") or b""
                if getattr(result, "exit_code", 1) == 0:
                    data = json.loads(output.decode("utf-8", errors="replace") or "{}")
                    self_state = data.get("Self") or {}
                    tailscale.update({
                        "backend_state": data.get("BackendState") or "unknown",
                        "online": self_state.get("Online"),
                        "tailscale_ips": self_state.get("TailscaleIPs") or [],
                        "peer_count": len(data.get("Peer") or {}),
                        "active_routes": self_state.get("PrimaryRoutes") or self_state.get("AllowedIPs") or [],
                    })
                else:
                    tailscale["issues"].append("tailscale status failed")
            except Exception as e:
                tailscale["issues"].append(f"status check failed: {e}")

    vpn_containers = []
    for name in ("protonvpn", "gluetun", "wireguard", "openvpn"):
        vc = docker_client.get_container_safe(name)
        if vc:
            vpn_containers.append({
                "name": vc.name,
                "status": vc.status,
                "image": vc.image.tags[0] if vc.image.tags else vc.image.short_id,
            })

    routed_apps = []
    routing_issues = []
    gluetun = docker_client.get_container_safe("gluetun")
    gluetun_id = gluetun.id if gluetun else ""
    try:
        all_containers = docker_client.client().containers.list(all=True)
    except Exception:
        all_containers = []
    vpn_names = {"gluetun", "protonvpn", "wireguard", "openvpn", "tailscale", "cloudflared", "traefik", "mediastack-rad"}
    for app in all_containers:
        if app.name in vpn_names:
            continue
        host_cfg = app.attrs.get("HostConfig", {}) or {}
        cfg = app.attrs.get("Config", {}) or {}
        labels = cfg.get("Labels", {}) or {}
        env = {}
        for entry in (cfg.get("Env", []) or []):
            if "=" in entry:
                k, _, v = entry.partition("=")
                env[k] = v
        expected = (
            labels.get("mediastack.rad.egress_vpn") == "gluetun"
            or labels.get("rad.egress_vpn") == "gluetun"
            or env.get("RAD_EGRESS_VPN") == "gluetun"
        )
        network_mode = str(host_cfg.get("NetworkMode") or "")
        actual = network_mode in {"service:gluetun", "container:gluetun", f"container:{gluetun_id}"}
        if expected or actual:
            row = {"name": app.name, "status": app.status, "expected": expected, "actual": actual, "network_mode": network_mode}
            routed_apps.append(row)
            if expected and not actual:
                routing_issues.append(f"{app.name} is marked for Gluetun but is not using Gluetun network mode")
            if actual and (not gluetun or gluetun.status != "running"):
                routing_issues.append(f"{app.name} uses Gluetun but Gluetun is not running")

    return {
        "tailscale": tailscale,
        "egress_vpn": {
            "present": bool(vpn_containers),
            "status": "running" if any(v["status"] == "running" for v in vpn_containers) else ("stopped" if vpn_containers else "not_configured"),
            "providers": vpn_containers,
            "routed_apps": routed_apps,
            "routing_issues": routing_issues,
        },
    }


# ---- Catalog & stack builder ----------------------------------------------


@app.get("/api/catalog")
async def api_catalog() -> dict:
    """Return all known services grouped by category for the builder UI."""
    result: dict[str, list[dict]] = {}
    for svc in catalog_mod.CATALOG.values():
        result.setdefault(svc.category, []).append({
            "key": svc.key,
            "display_name": svc.display_name,
            "description": svc.description,
            "image": svc.image,
            "web_port": svc.web_port,
            "cf_tunnel_unsuitable": svc.cf_tunnel_unsuitable,
            "cf_tunnel_warning": svc.cf_tunnel_warning,
        })
    # Stable ordering inside each category
    for cat in result:
        result[cat].sort(key=lambda s: s["display_name"].lower())
    return result


@app.post("/api/stack/generate")
async def api_stack_generate(req: StackRequest) -> dict:
    """Generate (but do not deploy) a compose file.

    Runs pre-generation validation and returns any issues alongside the YAML.
    Errors block generation; warnings are advisory.
    """
    if not req.domain:
        req.domain = _extract_core_domain_from_compose(config.stack_dir / "docker-compose.yml")

    validation = generator_mod.validate_request(req)
    if not validation.valid:
        raise HTTPException(400, {
            "message": "Request failed validation",
            "errors": [e.model_dump() for e in validation.errors],
        })
    try:
        text = generator_mod.generate(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    token_sources = _token_sources_for_request(req)
    return {
        "yaml": text,
        "bytes": len(text),
        "warnings": [w.model_dump() for w in validation.warnings],
        "token_sources": token_sources,
    }


@app.post("/api/stack/deploy")
async def api_stack_deploy(req: StackRequest) -> dict:
    """Generate, write, and bring up the stack."""
    if not req.domain:
        req.domain = _extract_core_domain_from_compose(config.stack_dir / "docker-compose.yml")

    validation = generator_mod.validate_request(req)
    if not validation.valid:
        raise HTTPException(400, {
            "message": "Deploy blocked — fix these errors first",
            "errors": [e.model_dump() for e in validation.errors],
        })
    try:
        path = generator_mod.write(req)
    except PermissionError as exc:
        logger.error("Deploy failed while writing compose file: %s", exc)
        hint = (
            "Set RAD_STACK_DIR and RAD_TRAEFIK_DIR to writable host paths and "
            "ensure the compose mount is not read-only."
        )
        if exc.filename:
            raise HTTPException(
                500,
                f"Permission denied while writing compose files at {exc.filename}. {hint}",
            )
        raise HTTPException(
            500,
            f"Permission denied while writing compose files: {exc}. {hint}",
        )
    except ValueError as e:
        raise HTTPException(400, f"Generation failed: {e}")

    token_sources = _token_sources_for_request(req)

    selected_service_names = {
        svc.key
        for svc in req.services
        if getattr(svc, "enabled", True)
    }

    # Also write traefik.yml if this deploy includes Traefik.
    has_traefik = any(s.key == "traefik" and s.enabled for s in req.services)
    if has_traefik or req.domain:
        traefik_yml = config.traefik_dir / "traefik.yml"
        traefik_yml.parent.mkdir(parents=True, exist_ok=True)
        # Use the stack owner's email for Let's Encrypt if available,
        # else fall back to a generic notice address.
        email = f"admin@{req.domain}" if req.domain else "admin@localhost"
        traefik_yml.write_text(
            generator_mod.generate_traefik_yaml(email=email)
        )
        # Ensure the letsencrypt dir exists with correct perms.
        acme_dir = traefik_yml.parent / "letsencrypt"
        acme_dir.mkdir(parents=True, exist_ok=True)
        acme = acme_dir / "acme.json"
        if not acme.exists():
            acme.touch()
        acme.chmod(0o600)

    # Run docker compose up -d using async subprocess so we don't block
    # the event loop. subprocess.run() is synchronous and would freeze all
    # WebSocket connections and health polls for up to 120s during a deploy.
    try:
        command_label, returncode, stdout, stderr = await _run_docker_compose_up(path)
        logger.info("Deploy used %s for compose up", command_label)
    except FileNotFoundError:
        raise HTTPException(500, "docker CLI not available in container")

    # Force a health check re-run after deploy so the UI reflects changes.
    await health_mod.cache.refresh()

    # Parse container name conflicts from Docker's output.
    # Docker reports: "The container name "/sonarr" is already in use..."
    # We extract names so the frontend can offer a one-click purge+retry.
    conflicts: list[str] = []
    if returncode != 0:
        # More robust regex to handle various Docker error message formats
        conflict_patterns = [
            r'container name ["\'\/]*(\w[\w.-]*)["\'\/]* is already in use',
            r'Conflict\. The container name ["\'\/]*(\w[\w.-]*)["\'\/]* is already in use',
        ]
        combined_output = stderr + stdout
        for pattern in conflict_patterns:
            for match in re.finditer(pattern, combined_output, re.IGNORECASE):
                name = match.group(1).lstrip("/")
                if name and name not in conflicts:
                    conflicts.append(name)

    route_warnings: list[dict[str, object]] = []
    if returncode == 0 and selected_service_names:
        # Best-effort guardrail: confirm new/selected web services have visible
        # Traefik routers after deploy. Non-blocking and warning-only.
        missing_services: list[dict[str, object]] = []
        for attempt in range(ROUTE_CHECK_ATTEMPTS):
            missing_services = await _services_missing_traefik_routes(path, selected_service_names)
            if not missing_services:
                break
            # Allow Traefik to warm up and reload before giving up.
            delay = ROUTE_CHECK_BASE_DELAY_SECONDS * (2 ** attempt / 2)
            if attempt < ROUTE_CHECK_ATTEMPTS - 1:
                await asyncio.sleep(min(delay, 8.0))

        if missing_services:
            route_warnings = []
            for item in missing_services:
                svc = str(item.get("service") or "")
                routes = sorted(set(item.get("routes", []))) if isinstance(item.get("routes"), list) else []
                route_warnings.append({
                    "service": svc,
                    "routes": routes,
                    "message": "Traefik router is not yet reported as enabled after deploy.",
                })

    return {
        "ok": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "path": str(path),
        "conflicts": conflicts,
        "route_warnings": route_warnings,
        "token_sources": token_sources,
    }



_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}$")


@app.post("/api/stack/purge-conflicts")
async def api_purge_conflicts(payload: dict) -> dict:
    """Stop and remove containers that are blocking a deploy.

    Accepts { "names": ["sonarr", "radarr", ...] }.
    Returns { "removed": [...], "errors": [...] }.

    Only removes containers whose names are explicitly provided —
    never performs a broad cleanup.
    """
    names: list[str] = payload.get("names") or []
    if not names:
        raise HTTPException(400, "No container names provided")

    # Validate each name to prevent injection or accidental broad removals.
    invalid = [n for n in names if not _CONTAINER_NAME_RE.match(str(n))]
    if invalid:
        raise HTTPException(422, f"Invalid container name(s): {', '.join(invalid)}")

    removed: list[str] = []
    errors: list[str] = []

    for name in names:
        try:
            c = docker_client.client().containers.get(name)
            if c.status == "running":
                c.stop(timeout=5)
            c.remove(force=True)
            removed.append(name)
            logger.info("Purged conflict container: %s", name)
        except Exception as e:
            errors.append(f"{name}: {e}")
            logger.warning("Could not purge %s: %s", name, e)

    return {"removed": removed, "errors": errors}


# ---- Health & checklist ---------------------------------------------------


@app.get("/api/health", response_model=HealthReport)
async def api_health(refresh: bool = False) -> HealthReport:
    """Return the current health report. ?refresh=true forces a re-run."""
    if refresh or health_mod.cache.current is None:
        return await health_mod.cache.refresh()
    return health_mod.cache.current


@app.post("/api/health/fix/{issue_id}")
async def api_health_fix(issue_id: str) -> dict:
    success, msg = health_mod.auto_fix(issue_id)
    if success:
        # Re-run health so the fixed issue drops off the list
        await health_mod.cache.refresh()
    return {"ok": success, "message": msg}


@app.post("/api/stack/port-check")
async def api_stack_port_check(req: StackRequest) -> dict:
    """Check selected services for host-port conflicts with running containers.

    Only checks against containers that are NOT part of the services being
    deployed — so redeploying the same stack never generates false positives.

    Returns { conflicts: [...], running_ports: {...} }.
    """
    # Get all running host ports, excluding services in this request
    # (they're being replaced, not competing)
    requesting_names = {s.key for s in req.services if s.enabled}
    running_ports: dict[int, str] = {}  # host_port → container_name
    try:
        containers = docker_client.client().containers.list()
        for c in containers:
            if c.name in requesting_names:
                continue  # skip — being replaced by this deploy
            bindings = (c.attrs.get("NetworkSettings") or {}).get("Ports") or {}
            for _, hosts in bindings.items():
                if not hosts:
                    continue
                for h in hosts:
                    try:
                        hp = int(h.get("HostPort") or 0)
                        if hp:
                            running_ports[hp] = c.name
                    except (TypeError, ValueError):
                        pass
    except Exception as e:
        logger.warning("Port check: cannot list containers: %s", e)

    conflicts = generator_mod.check_port_conflicts(req, running_ports)
    return {
        "conflicts": [c.model_dump() for c in conflicts],
        "running_ports": running_ports,
    }


@app.post("/api/utils/hash-password")
async def hash_password(payload: dict) -> dict:
    """Bcrypt-hash a password for use in Tinyauth USERS env var.

    Returns { hash: "$2b$10$..." } which the frontend combines with
    a username to produce the 'username:hash' format Tinyauth expects.
    """
    import bcrypt as _bcrypt
    password = (payload.get("password") or "").encode()
    if not password:
        raise HTTPException(400, "password is required")
    hashed = _bcrypt.hashpw(password, _bcrypt.gensalt(rounds=10))
    return {"hash": hashed.decode()}


@app.get("/api/traefik/routers")
async def traefik_routers():
    """Proxy Traefik's router list from the container network.

    The frontend used to fetch http://host:8081 directly, which is blocked
    as mixed content when RAD is served over HTTPS. This endpoint calls
    Traefik container-to-container (always HTTP on the Docker network) and
    returns the result, so the browser never makes a mixed-content request.
    """
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get("http://traefik:8081/api/http/routers")
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Traefik unreachable: {e}")


def _extract_host_rule(rule: str | None) -> str:
    m = re.search(r"Host\(`([^`]+)`\)", rule or "")
    return m.group(1) if m else ""


def _cert_covers_host(host: str, names: list[str]) -> bool:
    for name in names:
        if name == host:
            return True
        if name.startswith("*.") and host.endswith(name[1:]):
            return True
    return False


def _acme_domains() -> list[str]:
    acme = config.traefik_dir / "acme.json"
    if not acme.exists():
        return []
    try:
        data = json.loads(acme.read_text() or "{}")
    except Exception:
        return []
    names: list[str] = []
    for resolver in data.values():
        for cert in (resolver or {}).get("Certificates", []) or []:
            domain = cert.get("domain") or {}
            main = domain.get("main")
            if main:
                names.append(main)
            names.extend(domain.get("sans") or [])
    return names


@app.get("/api/traefik/route-status")
async def traefik_route_status() -> dict:
    """Return enriched route status for the Traefik table."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get("http://traefik:8081/api/http/routers")
            routers = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Traefik unreachable: {e}")

    cert_domains = _acme_domains()
    cloudflared = docker_client.get_container_safe("cloudflared")
    tunnel_state = "running" if cloudflared and cloudflared.status == "running" else ("stopped" if cloudflared else "missing")

    routes = []
    for router in routers:
        if router.get("name", "").endswith("@internal"):
            continue
        host = _extract_host_rule(router.get("rule"))
        addresses: list[str] = []
        dns_status = "unknown"
        if host:
            try:
                addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
                dns_status = "resolves" if addresses else "missing"
            except socket.gaierror:
                dns_status = "missing"
            except Exception:
                dns_status = "unknown"
        tls_config = "configured" if router.get("tls") else "off"
        cert_status = "covered" if host and _cert_covers_host(host, cert_domains) else ("missing" if host and cert_domains else "unknown")
        routes.append({
            "name": router.get("name"),
            "host": host,
            "service": router.get("service"),
            "router_status": router.get("status"),
            "tls_config": tls_config,
            "cert_status": cert_status,
            "dns_status": dns_status,
            "dns_addresses": addresses,
            "tunnel_status": "unknown" if tunnel_state == "running" else tunnel_state,
            "tunnel_detail": "Cloudflare public hostname mapping requires Zero Trust API access" if tunnel_state == "running" else f"cloudflared {tunnel_state}",
        })
    return {"cert_domains": cert_domains, "cloudflared": tunnel_state, "routes": routes}


@app.post("/api/custom-app/parse")
async def parse_custom_app(payload: dict) -> dict:
    """Parse a custom app from a URL or compose YAML fragment.

    Accepts:
      { "type": "url",     "content": "ghcr.io/author/app:latest" }
      { "type": "url",     "content": "https://github.com/owner/repo" }
      { "type": "compose", "content": "services:\\n  myapp:\\n    image: ..." }

    Returns:
      { "yaml": "<merged service yaml>", "services": [{"name": ..., "image": ..., "ports": [...]}] }
    """
    import re
    import yaml as _yaml

    source_type = payload.get("type", "url")
    content = (payload.get("content") or "").strip()

    if not content:
        raise HTTPException(400, "No content provided")

    raw_yaml = ""

    if source_type == "url":
        # ── GitHub repo URL → fetch docker-compose.yml from the repo ──────
        github_match = re.match(
            r"https?://github\.com/([^/]+/[^/\s]+?)(?:\.git)?/?$", content
        )
        if github_match:
            slug = github_match.group(1)
            fetched = False
            for branch in ("main", "master"):
                for filename in ("docker-compose.yml", "docker-compose.yaml"):
                    url = f"https://raw.githubusercontent.com/{slug}/{branch}/{filename}"
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as c:
                            r = await c.get(url)
                        if r.status_code == 200:
                            raw_yaml = r.text
                            fetched = True
                            break
                    except Exception:
                        continue
                if fetched:
                    break
            if not fetched:
                raise HTTPException(
                    404,
                    f"Could not find docker-compose.yml in {slug} "
                    f"(tried main/master branches). "
                    f"Paste the compose YAML directly in the 'Paste docker-compose' tab."
                )
        else:
            # ── Plain Docker image name / registry URL → generate minimal service ──
            # Normalise: strip protocol prefix if someone pastes a Docker Hub URL
            image = re.sub(r"^https?://hub\.docker\.com/r/", "", content)
            image = image.rstrip("/")
            # Derive a service name from the last path segment, strip tag
            name_part = image.split("/")[-1].split(":")[0]
            # Remove non-alphanumeric chars and limit length
            service_name = re.sub(r"[^a-z0-9-]", "-", name_part.lower())[:32].strip("-")
            raw_yaml = (
                f"services:\n"
                f"  {service_name}:\n"
                f"    image: {image}\n"
                f"    container_name: {service_name}\n"
                f"    restart: unless-stopped\n"
                f"    # TODO: add ports, volumes, and environment as needed\n"
                f"    # ports:\n"
                f"    #   - \"8080:8080\"\n"
                f"    # volumes:\n"
                f"    #   - ${{CONFIG_ROOT}}/{service_name}:/config\n"
            )

    elif source_type == "compose":
        raw_yaml = content
    else:
        raise HTTPException(400, f"Unknown type: {source_type!r}")

    # ── Parse the YAML and extract service summaries for the UI ───────────
    try:
        doc = _yaml.safe_load(raw_yaml) or {}
    except _yaml.YAMLError as e:
        raise HTTPException(400, f"YAML parse error: {e}")

    services_raw = doc.get("services") or {}
    if not services_raw:
        raise HTTPException(400, "No 'services:' block found in the compose file")

    services_summary = []
    for svc_name, svc in services_raw.items():
        if not isinstance(svc, dict):
            continue
        ports = []
        for p in (svc.get("ports") or []):
            s = str(p)
            # Grab only the host:container part (strip IP prefix if present)
            if ":" in s:
                ports.append(s.split(":")[-2] + ":" + s.split(":")[-1])
            else:
                ports.append(s)
        services_summary.append({
            "name": svc_name,
            "image": svc.get("image", ""),
            "ports": ports[:4],  # show at most 4 ports in the preview
        })

    return {
        "yaml": raw_yaml,
        "services": services_summary,
    }



# ---- Settings / Secrets ---------------------------------------------------


# Which secrets each service needs, in display order.
_SECRET_DEFS: list[dict] = [
    {
        "key": "CF_DNS_API_TOKEN",
        "label": "Cloudflare DNS API Token",
        "hint": "Zone:DNS:Edit + Zone:Zone:Read — used by Traefik for DNS-01 cert issuance",
        "service": "cloudflared",
        "link": "https://dash.cloudflare.com/profile/api-tokens",
    },
    {
        "key": "CLOUDFLARED_TOKEN",
        "label": "Cloudflare Tunnel Token",
        "hint": "From Zero Trust → Networks → Tunnels — authenticates the cloudflared daemon",
        "service": "cloudflared",
        "link": "https://one.dash.cloudflare.com/",
    },
    {
        "key": "TINYAUTH_AUTH_USERS",
        "label": "Tinyauth Users",
        "hint": "username:bcrypt_hash — use the Generate admin button in Stack Builder",
        "service": "tinyauth",
        "link": None,
    },
    {
        "key": "TINYAUTH_APPURL",
        "label": "Tinyauth App URL",
        "hint": "e.g. https://auth.nyrdalyrt.com — must match your CF Tunnel hostname",
        "service": "tinyauth",
        "link": None,
    },
    {
        "key": "TS_AUTHKEY",
        "label": "Tailscale Auth Key",
        "hint": "Reusable, non-ephemeral key from Tailscale admin",
        "service": "tailscale",
        "link": "https://login.tailscale.com/admin/settings/keys",
    },
    {
        "key": "VPN_SERVICE_PROVIDER",
        "label": "Gluetun Provider",
        "hint": "Provider key (e.g. ivpn, airvpn, custom). Required for Gluetun.",
        "service": "gluetun",
        "link": "https://github.com/qdm12/gluetun-wiki",
    },
    {
        "key": "WIREGUARD_PRIVATE_KEY",
        "label": "WireGuard Private Key",
        "hint": "Required for WireGuard setups. Leave empty for OpenVPN mode.",
        "service": "gluetun",
    },
    {
        "key": "WIREGUARD_ADDRESSES",
        "label": "WireGuard Addresses",
        "hint": "Required for WireGuard setups. Example: 10.64.222.21/32.",
        "service": "gluetun",
    },
    {
        "key": "OPENVPN_USER",
        "label": "OpenVPN User",
        "hint": "Required for OpenVPN setups.",
        "service": "gluetun",
        "link": None,
    },
    {
        "key": "OPENVPN_PASSWORD",
        "label": "OpenVPN Password",
        "hint": "Required for OpenVPN setups.",
        "service": "gluetun",
    },
    {
        "key": "SERVER_COUNTRIES",
        "label": "Gluetun server countries",
        "hint": "WireGuard mode requires server country selection; required unless using OpenVPN only.",
        "service": "gluetun",
    },
    {
        "key": "SERVER_REGION",
        "label": "Gluetun server regions",
        "hint": "Optional comma-separated server regions for Gluetun filtering.",
        "service": "gluetun",
    },
    {
        "key": "SERVER_CITIES",
        "label": "Gluetun server cities",
        "hint": "Optional comma-separated server cities for Gluetun filtering.",
        "service": "gluetun",
    },
    {
        "key": "SECURE_CORE_ONLY",
        "label": "Gluetun secure-core-only",
        "hint": "Optional Gluetun filter switch: 'on' when enabled.",
        "service": "gluetun",
    },
    {
        "key": "STREAM_ONLY",
        "label": "Gluetun stream-only",
        "hint": "Optional Gluetun filter switch: 'on' when enabled.",
        "service": "gluetun",
    },
    {
        "key": "PORT_FORWARD_ONLY",
        "label": "Gluetun port-forward-only",
        "hint": "Optional Gluetun filter switch: 'on' when enabled.",
        "service": "gluetun",
    },
    {
        "key": "PLEX_CLAIM",
        "label": "Plex Claim Token",
        "hint": "From plex.tv/claim — links this server to your account on first start (4 min expiry)",
        "service": "plex",
        "link": "https://plex.tv/claim",
    },
]


def _read_env_file() -> dict[str, str]:
    """Read the stack .env file and return key→value pairs."""
    env_path = config.stack_dir / ".env"
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def _env_value_is_set(raw: str) -> bool:
    """Return True when an environment value should be treated as present."""

    value = _unquote_env_value(raw).strip()
    if not value:
        return False
    return not bool(re.fullmatch(r"\$\{[A-Z0-9_]+(?::-[^}]*)?\}", value))


def _unquote_env_value(value: str) -> str:
    """Return an env value without surrounding quotes used by _write_env_file."""
    if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
        return value[1:-1]
    return value


def _mask_secret_value(value: str, min_chars: int = 4, max_chars: int = 24) -> str:
    """Return a redacted preview string for display in the UI."""
    if not value:
        return ""
    count = len(value)
    if count < min_chars:
        count = min_chars
    if count > max_chars:
        count = max_chars
    return "*" * count


def _quote_env_value(value: str) -> str:
    """Quote a .env value if it contains spaces, #, or other special chars."""
    if not value:
        return '""'
    if "'" in value or " " in value or "#" in value or "\n" in value or "\t" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


# Serialises all reads + writes to the stack .env file.
# Without this, a concurrent deploy and a settings save can interleave
# their read-then-write cycles and silently corrupt the file.
_env_file_lock = threading.Lock()


def _write_env_file(updates: dict[str, str]) -> None:
    """Write/update key=value pairs in the stack .env file.

    The module-level _env_file_lock is held for the entire read-modify-write
    cycle so concurrent calls (e.g. a deploy and a settings save arriving at
    the same time) cannot interleave and corrupt the file.
    """
    env_path = config.stack_dir / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    with _env_file_lock:
        existing_lines: list[str] = []
        if env_path.exists():
            existing_lines = env_path.read_text().splitlines()

        updated: set[str] = set()
        new_lines: list[str] = []

        for line in existing_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={_quote_env_value(updates[key])}")
                updated.add(key)
            else:
                new_lines.append(line)

        for key, value in updates.items():
            if key not in updated:
                new_lines.append(f"{key}={_quote_env_value(value)}")

        # Write atomically: temp file + rename so a crash mid-write
        # never leaves a half-written .env.
        tmp = env_path.with_suffix(".env.tmp")
        tmp.write_text("\n".join(new_lines) + "\n")
        tmp.replace(env_path)


def _token_source(value: str | None, env_value: str) -> str:
    if value and str(value).strip():
        return "request"
    if _env_value_is_set(env_value):
        return "env"
    return "missing"


def _token_sources_for_request(req: StackRequest) -> dict[str, str]:
    env = _read_env_file()
    return {
        "CF_DNS_API_TOKEN": _token_source(req.cloudflare_token, env.get("CF_DNS_API_TOKEN", "")),
        "CLOUDFLARED_TOKEN": _token_source(req.cloudflare_tunnel_token, env.get("CLOUDFLARED_TOKEN", "")),
    }


def _extract_domain_from_host_like(value: str) -> str:
    if not value:
        return ""
    candidate = str(value).strip()
    if candidate.startswith("*"):
        candidate = candidate[2:] if candidate.startswith("*.") else candidate[1:]
    candidate = re.sub(r"^https?://", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.split("?", 1)[0].split("/", 1)[0].split(":", 1)[0].strip()
    if not candidate or "." not in candidate:
        return ""
    return candidate.lower()


def _iter_traefik_rule_hosts(labels: object) -> list[str]:
    hosts: list[str] = []
    if labels is None:
        return hosts

    if isinstance(labels, dict):
        entries = list(labels.items())
    elif isinstance(labels, list):
        entries = []
        for item in labels:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, _, value = item.partition("=")
            entries.append((key, value))
    else:
        return hosts

    for key, value in entries:
        if not isinstance(key, str):
            continue
        if key.startswith("traefik.http.routers.") and ".rule" in key:
            host = _extract_host_rule(str(value))
            if host:
                hosts.append(host)
    return hosts


def _extract_core_domain_from_compose(compose_path: Path) -> str:
    if not compose_path.exists():
        return ""

    try:
        import yaml as _yaml

        doc = _yaml.safe_load(compose_path.read_text()) or {}
        services = doc.get("services") or {}
    except Exception:
        return ""

    if not isinstance(services, dict):
        return ""

    for cfg in services.values():
        if not isinstance(cfg, dict):
            continue
        for host in _iter_traefik_rule_hosts(cfg.get("labels")):
            domain = _extract_domain_from_host_like(host)
            if domain:
                return domain

    env = _read_env_file()
    app_url = env.get("TINYAUTH_APPURL")
    if app_url:
        domain = _extract_domain_from_host_like(_unquote_env_value(app_url))
        if domain:
            return domain

    return ""


def _services_in_compose() -> set[str]:
    """Return the set of service names in the deployed docker-compose.yml."""
    import yaml as _yaml
    compose_path = config.stack_dir / "docker-compose.yml"
    if not compose_path.exists():
        return set()
    try:
        doc = _yaml.safe_load(compose_path.read_text()) or {}
        return set((doc.get("services") or {}).keys())
    except Exception:
        return set()


def _router_names_from_labels(labels: object) -> list[str]:
    """Extract Traefik router names declared with `*.rule` labels."""
    lines: list[str] = []
    if isinstance(labels, dict):
        lines = [str(k) for k in labels.keys() if str(k).startswith("traefik.http.routers.")]
    elif isinstance(labels, list):
        lines = [str(v) for v in labels if isinstance(v, str)]
    if not lines:
        return []

    found: list[str] = []
    for item in lines:
        if not item.startswith("traefik.http.routers."):
            continue
        marker = ".rule=" if "=" in item else ".rule"
        idx = item.find(marker)
        if idx < 0:
            continue
        router_name = item[len("traefik.http.routers."):idx]
        if router_name and router_name not in found:
            found.append(router_name)
    return found


def _get_route_status(routers: dict[str, dict], route_name: str) -> str:
    """Read one router status from Traefik API payload regardless of provider suffix."""

    if not route_name:
        return ""
    for key in (f"{route_name}@docker", route_name):
        data = routers.get(key)
        if isinstance(data, dict) and "status" in data:
            return str(data.get("status") or "").lower()
    return ""


async def _services_missing_traefik_routes(compose_path: Path, selected_services: set[str] | None = None) -> list[dict[str, object]]:
    """Return services with expected Traefik routers that are not enabled yet.

    This is a non-blocking, best-effort post-deploy guardrail. It helps catch cases
    where a service was added with Traefik labels but Traefik API does not expose
    matching enabled routers after deployment.
    """
    if not compose_path.exists():
        return []

    try:
        import yaml as _yaml
        doc = _yaml.safe_load(compose_path.read_text()) or {}
        services = doc.get("services") or {}
    except Exception:
        return []

    if not isinstance(services, dict):
        return []

    selected = set(selected_services or set())
    if not selected:
        selected = set(services.keys())

    skip = {"traefik", "cloudflared", "tailscale", "tinyauth", "mediastack-rad"}
    try:
        routers = await checklist_mod._traefik_routers(force=True)
    except Exception:
        return []
    if not isinstance(routers, dict):
        return []

    missing: list[dict[str, object]] = []
    for name, cfg in services.items():
        if name in skip:
            continue
        if name not in selected and name not in cfg.get("container_name", name):
            continue
        if not isinstance(cfg, dict):
            continue
        expected_routes = _router_names_from_labels(cfg.get("labels"))
        if not expected_routes:
            continue
        not_found = [
            route
            for route in expected_routes
            if _get_route_status(routers, route) != "enabled"
        ]
        if not_found:
            missing.append({
                "service": name,
                "routes": sorted(set(not_found)),
            })

    return missing


@app.get("/api/settings/secrets")
async def api_secrets_list() -> list[SecretEntry]:
    """Return secrets relevant to the deployed stack with is_set status.

    Only shows secrets for services that are actually in the compose file.
    Never returns secret values — only whether each key is set.
    """
    deployed = _services_in_compose()
    env = _read_env_file()

    entries = []
    for defn in _SECRET_DEFS:
        # Show if service is deployed or if key is already set (legacy)
        if defn["service"] not in deployed and not env.get(defn["key"]):
            continue
        raw_value = env.get(defn["key"], "")
        entries.append(SecretEntry(
            key=defn["key"],
            label=defn["label"],
            hint=defn["hint"],
            service=defn["service"],
            is_set=bool(raw_value.strip()),
            masked_value=_mask_secret_value(_unquote_env_value(raw_value)) if raw_value.strip() else None,
            link=defn.get("link"),
        ))
    return entries


@app.get("/api/settings/secrets/{key}")
async def api_secret_value(key: str) -> SecretValue:
    """Return a secret value for explicit reveal.

    This endpoint only serves keys recognized by the settings model.
    Values are loaded from the stack `.env` file and unquoted for safe input
    rendering on the frontend.
    """
    if key not in _ALLOWED_ENV_KEYS:
        raise HTTPException(400, "Unsupported secret key")

    env = _read_env_file()
    raw_value = env.get(key, "")
    return SecretValue(
        key=key,
        value=_unquote_env_value(raw_value),
    )


@app.get("/api/settings/meta")
async def api_settings_meta() -> dict:
    """Return non-secret settings metadata for display in the UI."""
    stack_dir = config.stack_dir
    compose_path = stack_dir / "docker-compose.yml"
    return {
        "env_path": str(stack_dir / ".env"),
        "compose_path": str(compose_path),
        "stack_dir": str(stack_dir),
        "stack_dir_writable": _can_write_directory(stack_dir),
        "core_domain": _extract_core_domain_from_compose(compose_path),
    }


_ALLOWED_ENV_KEYS: set[str] = {
    k["key"] for k in _SECRET_DEFS
} | {
    "PUID", "PGID", "TZ",
    "TS_AUTHKEY", "TS_ROUTES", "TS_HOSTNAME",
    "VPN_SERVICE_PROVIDER", "VPN_TYPE", "WIREGUARD_PRIVATE_KEY", "WIREGUARD_ADDRESSES",
    "OPENVPN_USER", "OPENVPN_PASSWORD", "SERVER_COUNTRIES", "SERVER_REGION",
    "SERVER_CITIES", "SECURE_CORE_ONLY", "STREAM_ONLY", "PORT_FORWARD_ONLY",
    "TINYAUTH_LAN_SUBNET",
    "PLEX_TOKEN",
}


@app.post("/api/settings/secrets")
async def api_secrets_save(payload: dict) -> dict:
    """Save one or more secrets to the stack .env file.

    Accepts { key: value, ... }. Values are written as-is.
    Only keys in _ALLOWED_ENV_KEYS are accepted.
    Never logs or returns values. Returns { saved: [key, ...] }.
    """
    updates = {
        k: str(v) for k, v in payload.items()
        if k and isinstance(k, str) and k in _ALLOWED_ENV_KEYS
        and v is not None and str(v).strip()
    }
    if not updates:
        raise HTTPException(400, "No valid key=value pairs provided")
    try:
        _write_env_file(updates)
    except OSError as e:
        raise HTTPException(500, f"Could not write .env: {e}")
    return {"saved": list(updates.keys())}


@app.get("/api/checklist", response_model=list[ChecklistItem])
async def api_checklist() -> list[ChecklistItem]:
    return await checklist_mod.build_checklist()


# ---- WebSocket -------------------------------------------------------------


@app.websocket("/ws/stats")
async def ws_stats(ws: WebSocket) -> None:
    if config.api_key:
        token = ws.query_params.get("token", "")
        if token != config.api_key:
            await ws.close(code=4001, reason="Invalid or missing API key")
            return
    await ws_mod.stats_endpoint(ws)


# ---------------------------------------------------------------------------
# Static file mounting + SPA catch-all
#
# Order matters a lot here: the /assets mount must be registered before
# the catch-all, and the catch-all must be the very last thing added.
# The _verify_route_order call at the end of module import enforces this.
# ---------------------------------------------------------------------------


if config.static_dir.exists():
    # Serve built Vite assets (JS, CSS, images, fonts).
    app.mount(
        "/assets",
        StaticFiles(directory=config.static_dir / "assets"),
        name="assets",
    )


@app.get("/{full_path:path}")
async def spa_catchall(full_path: str) -> FileResponse:
    """Serve the Vue SPA for any route that isn't an API route.

    Because this handler is registered last and uses a `path` converter,
    it only matches after FastAPI has tried all the specific routes
    above. Unknown API paths still return 404 because /api/* handlers
    take precedence.
    """
    # /api/anything that wasn't caught by a handler above is a genuine
    # 404 — returning the SPA would mask frontend bugs.
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        raise HTTPException(404, f"No API route: /{full_path}")

    index = config.static_dir / "index.html"
    if not index.exists():
        return PlainTextResponse(
            "Frontend assets not found. This is a backend-only build. "
            "Run `npm run build` inside /app/frontend or pull the "
            "full image.",
            status_code=503,
        )
    return FileResponse(index)


def _verify_route_order() -> None:
    """Fail fast if any API route is declared after the SPA catch-all.

    This is the structural guarantee that the route ordering bug from
    our v1 can't sneak back in. A regression on this would break every
    API call silently — asserting here means the container just fails
    to start, which is loud and obvious.
    """
    seen_catchall = False
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            # The SPA catch-all route has path "/{full_path:path}".
            if route.path == "/{full_path:path}":
                seen_catchall = True
                continue
            if seen_catchall:
                raise RuntimeError(
                    f"Route ordering violation: {route.path} was declared "
                    f"after the SPA catch-all. Move it above spa_catchall "
                    f"in main.py."
                )


_verify_route_order()


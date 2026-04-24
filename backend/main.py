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
import logging
import re
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
from .models import SecretEntry, StackValidation
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
    """Return list of currently running container names."""
    all_c = docker_client.list_containers(include_stopped=False)
    return [c.name for c in all_c]


@app.post("/api/containers/{name}/start")
async def api_start(name: str) -> dict:
    docker_client.start(name)
    return {"ok": True}


@app.post("/api/containers/{name}/stop")
async def api_stop(name: str) -> dict:
    docker_client.stop(name)
    return {"ok": True}


@app.post("/api/containers/{name}/restart")
async def api_restart(name: str) -> dict:
    docker_client.restart(name)
    return {"ok": True}


@app.delete("/api/containers/{name}")
async def api_remove(name: str, force: bool = True) -> dict:
    docker_client.remove(name, force=force)
    return {"ok": True}


@app.post("/api/containers/{name}/logs")
async def api_logs(name: str, tail: int = 200) -> PlainTextResponse:
    c = docker_client.get_container_safe(name)
    if c is None:
        raise HTTPException(404, f"No container named {name}")
    logs = c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
    return PlainTextResponse(logs)


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
    return {
        "yaml": text,
        "bytes": len(text),
        "warnings": [w.model_dump() for w in validation.warnings],
    }


@app.post("/api/stack/deploy")
async def api_stack_deploy(req: StackRequest) -> dict:
    """Generate, write, and bring up the stack."""
    validation = generator_mod.validate_request(req)
    if not validation.valid:
        raise HTTPException(400, {
            "message": "Deploy blocked — fix these errors first",
            "errors": [e.model_dump() for e in validation.errors],
        })
    try:
        path = generator_mod.write(req)
    except ValueError as e:
        raise HTTPException(400, f"Generation failed: {e}")

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
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(path), "up", "-d",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=120
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise HTTPException(504, "docker compose up timed out after 2m")
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        returncode = proc.returncode
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

    return {
        "ok": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "path": str(path),
        "conflicts": conflicts,
    }



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


def _write_env_file(updates: dict[str, str]) -> None:
    """Write/update key=value pairs in the stack .env file."""
    env_path = config.stack_dir / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing lines to preserve comments and ordering
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text().splitlines()

    # Track which keys we've already updated
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
            new_lines.append(f"{key}={updates[key]}")
            updated.add(key)
        else:
            new_lines.append(line)

    # Append any new keys not already in the file
    for key, value in updates.items():
        if key not in updated:
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n")


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
        entries.append(SecretEntry(
            key=defn["key"],
            label=defn["label"],
            hint=defn["hint"],
            service=defn["service"],
            is_set=bool(env.get(defn["key"], "").strip()),
            link=defn.get("link"),
        ))
    return entries


@app.post("/api/settings/secrets")
async def api_secrets_save(payload: dict) -> dict:
    """Save one or more secrets to the stack .env file.

    Accepts { key: value, ... }. Values are written as-is.
    Never logs or returns values. Returns { saved: [key, ...] }.
    """
    updates = {
        k: str(v) for k, v in payload.items()
        if k and isinstance(k, str) and v is not None and str(v).strip()
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
    return checklist_mod.build_checklist()


# ---- WebSocket -------------------------------------------------------------


@app.websocket("/ws/stats")
async def ws_stats(ws: WebSocket) -> None:
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

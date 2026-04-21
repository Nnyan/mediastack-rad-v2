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
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import catalog as catalog_mod
from . import checklist as checklist_mod
from . import docker_client
from . import generator as generator_mod
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
    return docker_client.list_containers(all=all)


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
        })
    # Stable ordering inside each category
    for cat in result:
        result[cat].sort(key=lambda s: s["display_name"].lower())
    return result


@app.post("/api/stack/generate")
async def api_stack_generate(req: StackRequest) -> dict:
    """Generate (but do not deploy) a compose file. Returns the YAML text."""
    try:
        text = generator_mod.generate(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"yaml": text, "bytes": len(text)}


@app.post("/api/stack/deploy")
async def api_stack_deploy(req: StackRequest) -> dict:
    """Generate, write, and bring up the stack."""
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

    # Run docker compose up -d
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(path), "up", "-d"],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "docker compose up timed out after 2m")
    except FileNotFoundError:
        raise HTTPException(500, "docker CLI not available in container")

    # Force a health check re-run after deploy so the UI reflects changes.
    await health_mod.cache.refresh()

    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "path": str(path),
    }


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

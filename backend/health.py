"""System health checker — optimized.

Key design decisions:
  - _CheckContext: fetch all Docker state once per run (1 API call).
    Previously: 3 containers.list() + 6 get_container_safe() = 9+ calls.
  - Async checks run concurrently with asyncio.gather + 8s per-check timeout.
  - HealthCache.current is a plain attribute read — never blocks on a lock.
    Only concurrent refresh() calls serialize (rare; background loop is sole writer).
  - Tailscale TUN check uses HostConfig attrs instead of subprocess docker exec.
  - CF video streaming check gated on container actually running (not external Plex).
  - Fixed wrong env var name in fix_hint (was CLOUDFLARED_TOKEN, now CF_DNS_API_TOKEN).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

import httpx
import yaml

from . import docker_client
from .config import config
from .models import HealthIssue, HealthReport
from .validators import validate_compose_file, validate_env_file, validate_traefik_yaml

logger = logging.getLogger(__name__)


@dataclass
class _CheckContext:
    """Pre-fetched Docker state shared across all sync checks."""
    all_containers: list = field(default_factory=list)
    running_containers: list = field(default_factory=list)
    by_name: dict = field(default_factory=dict)

    @classmethod
    def fetch(cls) -> "_CheckContext":
        try:
            all_c = docker_client.client().containers.list(all=True)
        except Exception as e:
            logger.warning("Cannot list containers: %s", e)
            all_c = []
        running = [c for c in all_c if c.status == "running"]
        return cls(all_containers=all_c, running_containers=running,
                   by_name={c.name: c for c in all_c})

    def get(self, name: str):
        return self.by_name.get(name)

    def is_running(self, name: str) -> bool:
        c = self.by_name.get(name)
        return bool(c and c.status == "running")

    def env_of(self, name: str) -> dict[str, str]:
        c = self.by_name.get(name)
        if not c:
            return {}
        result = {}
        for entry in (c.attrs.get("Config", {}).get("Env", []) or []):
            if "=" in entry:
                k, _, v = entry.partition("=")
                result[k] = v  # last definition wins — Docker behaviour
        return result


def check_docker_socket(ctx: _CheckContext) -> list[HealthIssue]:
    if docker_client.ping():
        return []
    return [HealthIssue(
        id="docker.unreachable", severity="error", category="docker",
        title="Docker daemon unreachable",
        detail=(f"Cannot connect to Docker at {config.docker_socket}. "
                "Check that /var/run/docker.sock is mounted."),
        fix_hint="Verify docker.service is running and the socket is mounted.",
    )]


def check_compose_file(ctx: _CheckContext) -> list[HealthIssue]:
    compose = config.stack_dir / "docker-compose.yml"
    if not compose.exists():
        return [HealthIssue(
            id="compose.missing", severity="warning", category="config",
            title="No stack deployed yet",
            detail=f"{compose} does not exist. Use the Stack Builder to generate it.",
            fix_hint="Open the Stack Builder tab.",
        )]
    return [
        HealthIssue(
            id=f"compose.{i.severity}.{hash((i.line, i.message)) & 0xffff:x}",
            severity="error" if i.severity == "error" else "warning",
            category="config",
            title="Compose validation error" if i.severity == "error" else "Compose validation warning",
            detail=f"Line {i.line}: {i.message}" if i.line else i.message,
        )
        for i in validate_compose_file(compose)
    ]


def check_env_file(ctx: _CheckContext) -> list[HealthIssue]:
    return [
        HealthIssue(
            id=f"env.{i.severity}.{hash((i.line, i.message)) & 0xffff:x}",
            severity="error" if i.severity == "error" else "warning",
            category="config",
            title=f".env {i.severity}",
            detail=f"Line {i.line}: {i.message}" if i.line else i.message,
        )
        for i in validate_env_file(config.stack_dir / ".env")
    ]


def check_traefik_yaml(ctx: _CheckContext) -> list[HealthIssue]:
    t = config.traefik_dir / "traefik.yml"
    if not t.exists():
        return [HealthIssue(
            id="traefik.missing", severity="info", category="traefik",
            title="Traefik config not generated",
            detail=f"{t} not found. HTTPS will not work until it exists.",
            fix_hint="Configure domain + email in the Traefik tab.",
        )]
    return [
        HealthIssue(
            id=f"traefik.yml.{hash(i.message) & 0xffff:x}",
            severity="error" if i.severity == "error" else "warning",
            category="traefik",
            title=f"traefik.yml {i.severity}",
            detail=f"Line {i.line}: {i.message}" if i.line else i.message,
        )
        for i in validate_traefik_yaml(t)
    ]


def check_ghost_containers(ctx: _CheckContext) -> list[HealthIssue]:
    out = []
    for c in ctx.all_containers:
        if c.status in ("running", "restarting", "paused"):
            continue
        if "_" in c.name:
            prefix = c.name.partition("_")[0]
            if len(prefix) == 12 and all(ch in "0123456789abcdef" for ch in prefix):
                out.append(HealthIssue(
                    id=f"ghost.{c.id[:12]}", severity="warning", category="docker",
                    title=f"Ghost container: {c.name}",
                    detail=(f"{c.name!r} is stopped but blocking future deploys. "
                            f"Remove: docker rm -f {c.name}"),
                    fix_hint=f"docker rm -f {c.name}",
                    auto_fix_available=True,
                ))
    return out


def check_port_conflicts(ctx: _CheckContext) -> list[HealthIssue]:
    out, seen = [], {}
    for c in ctx.running_containers:
        bindings = (c.attrs.get("NetworkSettings", {}) or {}).get("Ports", {})
        for container_port, hosts in (bindings or {}).items():
            if not hosts:
                continue
            proto = container_port.split("/", 1)[-1] if "/" in container_port else "tcp"
            for h in hosts:
                hp = h.get("HostPort")
                if not hp:
                    continue
                key = f"{hp}/{proto}"
                if key in seen and seen[key] != c.name:
                    out.append(HealthIssue(
                        id=f"port.conflict.{key}", severity="error", category="docker",
                        title=f"Host port {key} conflict",
                        detail=f"Port {key} claimed by both {seen[key]} and {c.name}.",
                    ))
                else:
                    seen[key] = c.name
    return out


def check_acme_storage(ctx: _CheckContext) -> list[HealthIssue]:
    acme = config.traefik_dir / "letsencrypt" / "acme.json"
    if not acme.exists():
        return []
    mode = acme.stat().st_mode & 0o777
    if mode != 0o600:
        return [HealthIssue(
            id="acme.perms", severity="error", category="traefik",
            title=f"acme.json has wrong permissions ({oct(mode)})",
            detail="Traefik requires mode 0600. Cert issuance will fail until fixed.",
            fix_hint=f"chmod 600 {acme}",
            auto_fix_available=True,
        )]
    return []


def check_traefik_network(ctx: _CheckContext) -> list[HealthIssue]:
    traefik = ctx.get("traefik")
    if not traefik:
        return []
    t_networks = set(
        (traefik.attrs.get("NetworkSettings", {}) or {}).get("Networks", {}).keys()
    )
    if not t_networks:
        return []
    out = []
    for c in ctx.running_containers:
        if c.name == "traefik":
            continue
        labels = c.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("traefik.enable") != "true":
            continue
        c_networks = set(
            (c.attrs.get("NetworkSettings", {}) or {}).get("Networks", {}).keys()
        )
        if not (t_networks & c_networks):
            out.append(HealthIssue(
                id=f"traefik.net.{c.name}", severity="error", category="traefik",
                title=f"{c.name} is not on a Traefik network",
                detail=(
                    f"{c.name} has Traefik labels but no shared network with Traefik. "
                    f"Traefik: {', '.join(sorted(t_networks)) or '(none)'}. "
                    f"{c.name}: {', '.join(sorted(c_networks)) or '(none)'}."
                ),
                fix_hint=f"docker network connect {next(iter(t_networks))} {c.name}",
            ))
    return out


def check_cf_video_streaming(ctx: _CheckContext) -> list[HealthIssue]:
    """Plex/Jellyfin must not route through Cloudflare (ToS section 2.8).
    Only flags containers that are actually running in this stack.
    External Plex servers won't appear in ctx.by_name.
    """
    cf = ctx.get("cloudflared")
    if not cf or cf.status != "running":
        return []
    out = []
    for name, port in {"plex": "32400", "jellyfin": "8096"}.items():
        c = ctx.get(name)
        if not c or c.status != "running":
            continue
        labels = c.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("traefik.enable") == "true":
            out.append(HealthIssue(
                id=f"cf.video.{name}", severity="error", category="security",
                title=f"{name.title()} routed through Cloudflare — ToS violation risk",
                detail=(
                    f"{name.title()} has traefik.enable=true while Cloudflare Tunnel is running. "
                    "Cloudflare ToS section 2.8 prohibits proxying video streams — "
                    f"risks account suspension. Use Tailscale, Plex relay, or port-forward {port}."
                ),
                fix_hint=f"Remove traefik.enable=true from {name} labels and recreate.",
            ))
    return out


def check_tailscale(ctx: _CheckContext) -> list[HealthIssue]:
    ts = ctx.get("tailscale")
    if not ts:
        return []
    out = []
    if ts.status != "running":
        out.append(HealthIssue(
            id="tailscale.not_running", severity="error", category="network",
            title="Tailscale container is not running",
            detail=f"State: '{ts.status}'. Check: docker logs tailscale",
            fix_hint="docker start tailscale",
            auto_fix_available=True,
        ))
        return out

    env = ctx.env_of("tailscale")
    authkey = env.get("TS_AUTHKEY", "")
    if not authkey or authkey in ("${TS_AUTHKEY}", ""):
        out.append(HealthIssue(
            id="tailscale.no_authkey", severity="error", category="network",
            title="TS_AUTHKEY not set on Tailscale container",
            detail=("Tailscale needs an auth key. Generate a reusable, non-ephemeral key at "
                    "https://login.tailscale.com/admin/settings/keys"),
            fix_hint="Set TS_AUTHKEY in your compose file and recreate.",
        ))

    # Check TUN via HostConfig attrs — no subprocess/docker exec needed
    if env.get("TS_USERSPACE", "false") == "false":
        host_cfg = ts.attrs.get("HostConfig", {}) or {}
        devices = host_cfg.get("Devices") or []
        has_tun = any("/dev/net/tun" in str(d.get("PathOnHost", "")) for d in devices)
        has_cap = "NET_ADMIN" in (host_cfg.get("CapAdd") or [])
        if not has_tun or not has_cap:
            missing = []
            if not has_cap:
                missing.append("cap_add: [NET_ADMIN, NET_RAW]")
            if not has_tun:
                missing.append("devices: [/dev/net/tun:/dev/net/tun]")
            out.append(HealthIssue(
                id="tailscale.no_tun", severity="warning", category="network",
                title="Tailscale missing TUN configuration",
                detail=f"TS_USERSPACE=false requires: {', '.join(missing)}.",
                fix_hint="Redeploy via Stack Builder — it adds these automatically.",
            ))
    return out


async def check_cloudflare_token(ctx: _CheckContext) -> list[HealthIssue]:
    """Validate the CF token actually loaded into Traefik.
    Uses pre-fetched ctx.env_of() — no additional Docker call.
    """
    traefik = ctx.get("traefik")
    if not traefik:
        return []

    env = ctx.env_of("traefik")
    token = env.get("CF_DNS_API_TOKEN", "").strip()
    if not token:
        return [HealthIssue(
            id="cloudflare.token.missing", severity="error", category="traefik",
            title="CF_DNS_API_TOKEN not set on Traefik",
            detail=("No CF_DNS_API_TOKEN in Traefik — DNS-01 cert issuance will fail. "
                    "Check for duplicate entries; Docker uses the last definition silently."),
            fix_hint="Set CF_DNS_API_TOKEN under the traefik service in your compose file.",
        )]

    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
        if not r.json().get("success"):
            return [HealthIssue(
                id="cloudflare.token.invalid", severity="error", category="traefik",
                title="CF_DNS_API_TOKEN is invalid or revoked",
                detail="Cloudflare rejected the token. Regenerate with Zone:DNS:Edit + Zone:Zone:Read.",
                fix_hint="https://dash.cloudflare.com/profile/api-tokens",
            )]
    except httpx.HTTPError as e:
        return [HealthIssue(
            id="cloudflare.api.unreachable", severity="warning", category="traefik",
            title="Cannot reach Cloudflare API",
            detail=f"Token validation failed (network): {e}",
        )]
    return []


SYNC_CHECKS: list[Callable[[_CheckContext], list[HealthIssue]]] = [
    check_docker_socket,
    check_compose_file,
    check_env_file,
    check_traefik_yaml,
    check_ghost_containers,
    check_port_conflicts,
    check_acme_storage,
    check_traefik_network,
    check_cf_video_streaming,
    check_tailscale,
]

ASYNC_CHECKS = [check_cloudflare_token]


async def run_checks() -> HealthReport:
    start = time.monotonic()
    issues: list[HealthIssue] = []

    ctx = _CheckContext.fetch()  # one Docker call, shared by all checks

    for check in SYNC_CHECKS:
        try:
            issues.extend(check(ctx))
        except Exception as e:
            logger.exception("Check %s failed", check.__name__)
            issues.append(HealthIssue(
                id=f"check.crash.{check.__name__}", severity="warning", category="internal",
                title=f"Check '{check.__name__}' crashed", detail=str(e),
            ))

    async def _run_async(check):
        try:
            return await asyncio.wait_for(check(ctx), timeout=8.0)
        except asyncio.TimeoutError:
            return [HealthIssue(
                id=f"check.timeout.{check.__name__}", severity="warning", category="network",
                title=f"Check '{check.__name__}' timed out (>8s)",
                detail="Network call did not complete. Check connectivity.",
            )]
        except Exception as e:
            logger.exception("Async check %s failed", check.__name__)
            return []

    for result in await asyncio.gather(*[_run_async(c) for c in ASYNC_CHECKS]):
        issues.extend(result)

    summary: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for i in issues:
        summary[i.severity] = summary.get(i.severity, 0) + 1

    return HealthReport(
        ok=(summary["error"] == 0),
        checked_at=time.time(),
        duration_ms=int((time.monotonic() - start) * 1000),
        issues=issues,
        summary=summary,
    )


def auto_fix(issue_id: str) -> tuple[bool, str]:
    if issue_id.startswith("ghost."):
        cid = issue_id.split(".", 1)[1]
        try:
            c = docker_client.get_container_safe(cid)
            if c:
                c.remove(force=True)
                return True, f"Removed ghost container {c.name}"
            return False, "Container already gone"
        except Exception as e:
            return False, f"Could not remove: {e}"
    if issue_id == "acme.perms":
        acme = config.traefik_dir / "letsencrypt" / "acme.json"
        try:
            acme.chmod(0o600)
            return True, "Set acme.json to mode 0600"
        except OSError as e:
            return False, f"chmod failed: {e}"
    if issue_id == "tailscale.not_running":
        try:
            docker_client.start("tailscale")
            return True, "Started tailscale"
        except Exception as e:
            return False, f"Could not start: {e}"
    return False, "No auto-fix available for this issue"


class HealthCache:
    """Read/write separated cache.

    .current is a plain attribute read — never acquires the lock.
    .refresh() acquires the lock so concurrent refreshes serialize
    rather than running duplicate check sets.
    """

    def __init__(self) -> None:
        self._report: HealthReport | None = None
        self._lock = asyncio.Lock()

    @property
    def current(self) -> HealthReport | None:
        return self._report  # safe plain read in CPython

    async def refresh(self) -> HealthReport:
        async with self._lock:
            self._report = await run_checks()
            return self._report

    async def start_loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("Health check loop error")
            await asyncio.sleep(config.health_interval)


cache = HealthCache()

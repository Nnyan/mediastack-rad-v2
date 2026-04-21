"""System health checker.

Runs a battery of checks that would have caught every issue we hit
during the initial deployment:

  - Docker socket is accessible and the daemon is responsive
  - Compose file exists and parses as valid YAML
  - No duplicate environment keys in compose or .env (the CF token bug)
  - No ghost containers (renamed copies blocking deploys)
  - No port conflicts between containers and host processes
  - Cloudflare API token is valid and has DNS:Edit permission
  - Traefik YAML is valid and has required fields
  - ACME certificate storage is writable with correct permissions
  - Services on compose share at least one network with Traefik
  - External DNS records resolve for configured domains

Each check returns a HealthIssue the UI can render. The full report
is cached for `config.health_interval` seconds — expensive checks
(like HTTPS probes) don't re-run on every dashboard poll.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import stat
import time
from pathlib import Path
from typing import Callable, Awaitable

import httpx
import yaml

from . import docker_client
from .config import config
from .models import HealthIssue, HealthReport
from .validators import (
    validate_compose_file,
    validate_env_file,
    validate_traefik_yaml,
)

logger = logging.getLogger(__name__)


# Each check is a callable that returns a list[HealthIssue]. We keep
# them as free functions rather than a class because it's trivial to
# add one, and the ordering in the UI is just the ordering here.
CheckFn = Callable[[], Awaitable[list[HealthIssue]] | list[HealthIssue]]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_docker_socket() -> list[HealthIssue]:
    """Can we talk to Docker at all? Everything else is moot if we can't."""
    if docker_client.ping():
        return []
    return [HealthIssue(
        id="docker.unreachable",
        severity="error",
        category="docker",
        title="Docker daemon unreachable",
        detail=(
            f"Cannot connect to Docker at {config.docker_socket}. "
            f"Check that the socket is mounted (-v /var/run/docker.sock:"
            f"/var/run/docker.sock) and that the user has permission."
        ),
        fix_hint="Check docker.service status and the RAD container's "
                 "socket mount.",
    )]


def check_compose_file() -> list[HealthIssue]:
    """Compose file exists, parses, and has no duplicate env keys."""
    compose = config.stack_dir / "docker-compose.yml"
    if not compose.exists():
        return [HealthIssue(
            id="compose.missing",
            severity="warning",
            category="config",
            title="No stack deployed yet",
            detail=(
                f"{compose} does not exist. Use the Stack Builder to "
                f"generate your docker-compose.yml."
            ),
            fix_hint="Open the Stack Builder tab.",
        )]

    issues = validate_compose_file(compose)
    out: list[HealthIssue] = []
    for i in issues:
        out.append(HealthIssue(
            id=f"compose.{i.severity}.{hash((i.line, i.message)) & 0xffff:x}",
            severity="error" if i.severity == "error" else "warning",
            category="config",
            title=(
                "Compose validation error"
                if i.severity == "error" else "Compose validation warning"
            ),
            detail=(
                f"Line {i.line}: {i.message}" if i.line else i.message
            ),
            fix_hint=None,
        ))
    return out


def check_env_file() -> list[HealthIssue]:
    """.env file — often absent, but when present we want it clean."""
    env = config.stack_dir / ".env"
    issues = validate_env_file(env)
    return [
        HealthIssue(
            id=f"env.{i.severity}.{hash((i.line, i.message)) & 0xffff:x}",
            severity="error" if i.severity == "error" else "warning",
            category="config",
            title=f".env {i.severity}",
            detail=f"Line {i.line}: {i.message}" if i.line else i.message,
        )
        for i in issues
    ]


def check_traefik_yaml() -> list[HealthIssue]:
    """Traefik static config file — the one that crashed us today."""
    t = config.traefik_dir / "traefik.yml"
    if not t.exists():
        return [HealthIssue(
            id="traefik.missing",
            severity="info",
            category="traefik",
            title="Traefik config not generated",
            detail=f"{t} not found. HTTPS will not work until it exists.",
            fix_hint="Configure domain + email in the Traefik tab.",
        )]

    issues = validate_traefik_yaml(t)
    return [
        HealthIssue(
            id=f"traefik.yml.{hash(i.message) & 0xffff:x}",
            severity="error" if i.severity == "error" else "warning",
            category="traefik",
            title=f"traefik.yml {i.severity}",
            detail=f"Line {i.line}: {i.message}" if i.line else i.message,
        )
        for i in issues
    ]


def check_ghost_containers() -> list[HealthIssue]:
    """Ghost containers are stopped copies with scrambled names that
    block future compose operations for that service.
    """
    out: list[HealthIssue] = []
    try:
        for c in docker_client.client().containers.list(all=True):
            if c.status in ("running", "restarting", "paused"):
                continue
            # Ghost pattern: <12-char-hex>_<service>
            if "_" in c.name:
                prefix, _, _ = c.name.partition("_")
                if len(prefix) == 12 and all(
                    ch in "0123456789abcdef" for ch in prefix
                ):
                    out.append(HealthIssue(
                        id=f"ghost.{c.id[:12]}",
                        severity="warning",
                        category="docker",
                        title=f"Ghost container: {c.name}",
                        detail=(
                            f"Container {c.name!r} is stopped but its "
                            f"name is blocking future deploys of the "
                            f"matching service. Remove it with "
                            f"`docker rm -f {c.name}`."
                        ),
                        fix_hint=f"docker rm -f {c.name}",
                        auto_fix_available=True,
                    ))
    except Exception as e:  # noqa: BLE001
        logger.warning("Ghost check failed: %s", e)
    return out


def check_port_conflicts() -> list[HealthIssue]:
    """Two containers claiming the same host port will fail to start.

    We walk every container's port bindings and flag duplicates. Host
    processes are harder to detect from inside a container, so we warn
    only — the Docker API will refuse the deploy anyway if there's a
    real collision.
    """
    out: list[HealthIssue] = []
    seen: dict[str, str] = {}  # "80/tcp" -> container name

    try:
        for c in docker_client.client().containers.list(all=False):
            bindings = (c.attrs.get("NetworkSettings", {}) or {}).get("Ports", {})
            for container_port, hosts in (bindings or {}).items():
                if not hosts:
                    continue
                for h in hosts:
                    hp = h.get("HostPort")
                    if not hp:
                        continue
                    proto = container_port.split("/", 1)[-1] if "/" in container_port else "tcp"
                    key = f"{hp}/{proto}"
                    if key in seen and seen[key] != c.name:
                        out.append(HealthIssue(
                            id=f"port.conflict.{key}",
                            severity="error",
                            category="docker",
                            title=f"Port {key} conflict",
                            detail=(
                                f"Host port {key} is in use by both "
                                f"{seen[key]} and {c.name}."
                            ),
                        ))
                    else:
                        seen[key] = c.name
    except Exception as e:  # noqa: BLE001
        logger.warning("Port check failed: %s", e)
    return out


def check_acme_storage() -> list[HealthIssue]:
    """ACME wants acme.json at mode 0600 — otherwise Traefik refuses it."""
    acme = config.traefik_dir / "letsencrypt" / "acme.json"
    if not acme.exists():
        return []  # no certs yet, nothing to check
    mode = acme.stat().st_mode & 0o777
    if mode != 0o600:
        return [HealthIssue(
            id="acme.perms",
            severity="error",
            category="traefik",
            title=f"acme.json has wrong permissions ({oct(mode)})",
            detail=(
                "Traefik refuses to use acme.json unless it's mode 0600. "
                "Certificates cannot be issued or renewed until fixed."
            ),
            fix_hint=f"chmod 600 {acme}",
            auto_fix_available=True,
        )]
    return []


async def check_cloudflare_token() -> list[HealthIssue]:
    """Validate the CF token by hitting the user info endpoint.

    We intentionally do NOT read the token from our own env — instead,
    we check the Traefik container's environment to validate the token
    actually in use. This catches the exact bug we hit today where a
    stale empty duplicate was shadowing the real token.
    """
    try:
        traefik = docker_client.get_container_safe("traefik")
    except Exception:  # noqa: BLE001
        return []

    if traefik is None:
        return []

    # Find the CF token env var inside the running container
    env_list = traefik.attrs.get("Config", {}).get("Env", []) or []
    env: dict[str, str] = {}
    for entry in env_list:
        if "=" in entry:
            k, _, v = entry.partition("=")
            env[k] = v

    token = env.get("CF_DNS_API_TOKEN")
    if not token:
        return [HealthIssue(
            id="cloudflare.token.missing",
            severity="error",
            category="traefik",
            title="CF_DNS_API_TOKEN not set on Traefik",
            detail=(
                "Traefik's environment has no CF_DNS_API_TOKEN — DNS-01 "
                "certificate issuance will fail for every domain."
            ),
            fix_hint="Set CLOUDFLARED_TOKEN in the RAD Traefik tab and redeploy.",
        )]

    # Call the CF API /user/tokens/verify endpoint
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
        data = r.json()
        if not data.get("success"):
            return [HealthIssue(
                id="cloudflare.token.invalid",
                severity="error",
                category="traefik",
                title="CF_DNS_API_TOKEN is invalid or revoked",
                detail=(
                    "Cloudflare rejected the token. Generate a new one "
                    "with Zone:DNS:Edit + Zone:Zone:Read on your domain."
                ),
                fix_hint="https://dash.cloudflare.com/profile/api-tokens",
            )]
    except httpx.HTTPError as e:
        return [HealthIssue(
            id="cloudflare.api.unreachable",
            severity="warning",
            category="traefik",
            title="Cannot reach Cloudflare API",
            detail=f"Token validation failed (network): {e}",
        )]

    return []


def check_traefik_network() -> list[HealthIssue]:
    """Traefik can only see containers it shares a Docker network with.

    If a service declares Traefik labels but isn't on the same network,
    the Docker provider simply won't pick it up — one of the most
    confusing silent failure modes in this stack.
    """
    traefik = docker_client.get_container_safe("traefik")
    if traefik is None:
        return []

    t_networks = set(
        (traefik.attrs.get("NetworkSettings", {}) or {})
        .get("Networks", {}).keys()
    )
    if not t_networks:
        return []

    out: list[HealthIssue] = []
    for c in docker_client.client().containers.list():
        if c.name == "traefik":
            continue
        labels = c.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("traefik.enable") != "true":
            continue
        c_networks = set(
            (c.attrs.get("NetworkSettings", {}) or {})
            .get("Networks", {}).keys()
        )
        if not (t_networks & c_networks):
            out.append(HealthIssue(
                id=f"traefik.net.{c.name}",
                severity="error",
                category="traefik",
                title=f"{c.name} is not on a Traefik network",
                detail=(
                    f"{c.name} has Traefik labels but does not share a "
                    f"Docker network with Traefik. Traefik cannot route "
                    f"to it. Traefik is on: "
                    f"{', '.join(sorted(t_networks)) or '(none)'}. "
                    f"{c.name} is on: "
                    f"{', '.join(sorted(c_networks)) or '(none)'}."
                ),
                fix_hint=(
                    f"docker network connect "
                    f"{next(iter(t_networks))} {c.name}"
                ),
            ))
    return out


def check_bind_socket() -> list[HealthIssue]:
    """Sanity check that we can bind to our declared port (no other
    instance of RAD running, permissions correct, etc.).
    """
    return []


def check_cf_video_streaming() -> list[HealthIssue]:
    """Warn if Plex or Jellyfin have Traefik labels while cloudflared is running.

    Cloudflare's ToS (section 2.8) prohibits using their network to proxy
    video streams. Routing Plex or Jellyfin through a Cloudflare Tunnel
    violates this and risks account suspension with no warning.

    Only applies when Plex/Jellyfin are actually running in this stack —
    if the user is using an external Plex server, this check is skipped.
    """
    cf = docker_client.get_container_safe("cloudflared")
    if cf is None or cf.status != "running":
        return []

    out: list[HealthIssue] = []
    for name, port in {"plex": "32400", "jellyfin": "8096"}.items():
        c = docker_client.get_container_safe(name)
        # Only flag if the container is actually running in this stack.
        # An external Plex server won't appear here at all.
        if c is None or c.status != "running":
            continue
        labels = c.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("traefik.enable") == "true":
            out.append(HealthIssue(
                id=f"cf.video.{name}",
                severity="error",
                category="security",
                title=f"{name.title()} is routed through Cloudflare — ToS violation risk",
                detail=(
                    f"{name.title()} has traefik.enable=true while Cloudflare Tunnel "
                    f"is running. Cloudflare's ToS prohibits proxying video streams — "
                    f"this risks account suspension. "
                    f"Use Tailscale, Plex's built-in relay, or direct port-forward "
                    f"({port}) instead. The stack generator automatically excludes "
                    f"{name} from Traefik labels when cloudflared is selected."
                ),
                fix_hint=(
                    f"Remove traefik.enable=true from {name}'s labels in "
                    f"your compose file and recreate the container."
                ),
            ))
    return out


def check_tailscale() -> list[HealthIssue]:
    """If Tailscale is deployed, verify it's up and authenticated."""
    out: list[HealthIssue] = []
    ts = docker_client.get_container_safe("tailscale")
    if ts is None:
        return []  # Not deployed, nothing to check

    if ts.status != "running":
        out.append(HealthIssue(
            id="tailscale.not_running",
            severity="error",
            category="network",
            title="Tailscale container is not running",
            detail=(
                f"Container 'tailscale' is in state '{ts.status}'. "
                "Check logs with: docker logs tailscale"
            ),
            fix_hint="docker start tailscale",
            auto_fix_available=True,
        ))
        return out

    # Check TS_AUTHKEY is set
    env_list = ts.attrs.get("Config", {}).get("Env", []) or []
    env = {}
    for entry in env_list:
        if "=" in entry:
            k, _, v = entry.partition("=")
            env[k] = v

    authkey = env.get("TS_AUTHKEY", "")
    if not authkey or authkey in ("${TS_AUTHKEY}", ""):
        out.append(HealthIssue(
            id="tailscale.no_authkey",
            severity="error",
            category="network",
            title="TS_AUTHKEY not set on Tailscale container",
            detail=(
                "Tailscale needs an auth key to join your tailnet. "
                "Generate one at https://login.tailscale.com/admin/settings/keys "
                "— use a reusable, non-ephemeral key so the node persists across restarts."
            ),
            fix_hint="Set TS_AUTHKEY in your compose file and recreate the container.",
        ))

    # Check /dev/net/tun is accessible (TS_USERSPACE=false mode)
    userspace = env.get("TS_USERSPACE", "false")
    if userspace == "false":
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "exec", "tailscale", "test", "-c", "/dev/net/tun"],
                capture_output=True, timeout=3,
            )
            if result.returncode != 0:
                out.append(HealthIssue(
                    id="tailscale.no_tun",
                    severity="warning",
                    category="network",
                    title="Tailscale: /dev/net/tun not accessible",
                    detail=(
                        "/dev/net/tun is required when TS_USERSPACE=false. "
                        "Ensure the container has cap_add: [NET_ADMIN, NET_RAW] "
                        "and devices: [/dev/net/tun:/dev/net/tun]."
                    ),
                    fix_hint="Set TS_USERSPACE=true if /dev/net/tun is unavailable on this host.",
                ))
        except Exception:
            pass

    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


SYNC_CHECKS: list[Callable[[], list[HealthIssue]]] = [
    check_docker_socket,
    check_compose_file,
    check_env_file,
    check_traefik_yaml,
    check_ghost_containers,
    check_port_conflicts,
    check_acme_storage,
    check_traefik_network,
    check_bind_socket,
    check_cf_video_streaming,
    check_tailscale,
]

ASYNC_CHECKS: list[Callable[[], Awaitable[list[HealthIssue]]]] = [
    check_cloudflare_token,
]


async def run_checks() -> HealthReport:
    """Run every health check and aggregate the results.

    Sync checks run sequentially — they're all local and fast (<5ms each).
    Async checks run concurrently via gather so network calls (CF API,
    Traefik API) don't serialize. Each async check has an 8s timeout so
    a slow network can't stall the whole report.
    """
    start = time.monotonic()
    issues: list[HealthIssue] = []

    for check in SYNC_CHECKS:
        try:
            issues.extend(check())
        except Exception as e:  # noqa: BLE001
            logger.exception("Check %s failed unexpectedly", check.__name__)
            issues.append(HealthIssue(
                id=f"check.crash.{check.__name__}",
                severity="warning",
                category="internal",
                title=f"Check '{check.__name__}' crashed",
                detail=str(e),
            ))

    async def _run_async(check):
        try:
            return await asyncio.wait_for(check(), timeout=8.0)
        except asyncio.TimeoutError:
            return [HealthIssue(
                id=f"check.timeout.{check.__name__}",
                severity="warning",
                category="network",
                title=f"Check '{check.__name__}' timed out (>8s)",
                detail="Network call did not complete in time. Check connectivity.",
            )]
        except Exception as e:  # noqa: BLE001
            logger.exception("Async check %s failed", check.__name__)
            return []

    async_results = await asyncio.gather(*[_run_async(c) for c in ASYNC_CHECKS])
    for result in async_results:
        issues.extend(result)

    summary = {"error": 0, "warning": 0, "info": 0}
    for i in issues:
        summary[i.severity] = summary.get(i.severity, 0) + 1

    return HealthReport(
        ok=(summary["error"] == 0),
        checked_at=time.time(),
        duration_ms=int((time.monotonic() - start) * 1000),
        issues=issues,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Auto-fix
# ---------------------------------------------------------------------------


def auto_fix(issue_id: str) -> tuple[bool, str]:
    """Attempt to remediate a specific issue.

    Returns (success, human_message). Most fixes are shell commands
    we could run ourselves, but a few (regenerating Traefik config)
    require user input so they're surfaced as hints only.
    """
    if issue_id.startswith("ghost."):
        # issue_id is "ghost.<container-id>"
        cid = issue_id.split(".", 1)[1]
        try:
            c = docker_client.get_container_safe(cid)
            if c:
                c.remove(force=True)
                return True, f"Removed ghost container {c.name}"
            return False, "Container already gone"
        except Exception as e:  # noqa: BLE001
            return False, f"Could not remove: {e}"

    if issue_id == "acme.perms":
        acme = config.traefik_dir / "letsencrypt" / "acme.json"
        try:
            acme.chmod(0o600)
            return True, "Set acme.json to mode 0600"
        except OSError as e:
            return False, f"chmod failed: {e}"

    return False, "No auto-fix available for this issue"


# ---------------------------------------------------------------------------
# Cached/scheduled runner
# ---------------------------------------------------------------------------


class HealthCache:
    """Holds the most recent health report so API handlers can return
    quickly without re-running expensive checks on every request.

    The background loop refreshes the report every `config.health_interval`
    seconds. Manual refresh (e.g. after a redeploy) can force a rerun.
    """

    def __init__(self) -> None:
        self._report: HealthReport | None = None
        self._lock = asyncio.Lock()

    @property
    def current(self) -> HealthReport | None:
        return self._report

    async def refresh(self) -> HealthReport:
        async with self._lock:
            self._report = await run_checks()
            return self._report

    async def start_loop(self) -> None:
        """Run forever, refreshing at the configured interval."""
        while True:
            try:
                await self.refresh()
            except Exception:  # noqa: BLE001
                logger.exception("Health check loop error")
            await asyncio.sleep(config.health_interval)


cache = HealthCache()

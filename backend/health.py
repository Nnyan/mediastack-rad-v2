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
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

import httpx
import yaml

from . import docker_client
from .config import config
from .models import CheckResult, HealthIssue, HealthReport
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
            title=f"Env file {i.severity}",
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
            title=f"Traefik.yml {i.severity}",
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




def check_tailscale(ctx: _CheckContext) -> list[HealthIssue]:
    ts = ctx.get("tailscale")
    if not ts:
        return []
    out = []
    if ts.status != "running":
        out.append(HealthIssue(
            id="tailscale.not_running", severity="error", category="Network",
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
            id="tailscale.no_authkey", severity="error", category="Network",
            title="TS_AUTHKEY not set on Tailscale container",
            detail=("Tailscale needs an auth key. Generate a reusable, non-ephemeral key at "
                    "https://login.tailscale.com/admin/settings/keys"),
            fix_hint="Set TS_AUTHKEY in your compose file and recreate.",
        ))

    userspace = env.get("TS_USERSPACE", "false").lower()
    if userspace != "false":
        out.append(HealthIssue(
            id="tailscale.userspace_mode", severity="warning", category="Network",
            title="Tailscale not in kernel mode",
            detail="TS_USERSPACE should be false for subnet routing and direct tunnel access.",
            fix_hint="Redeploy Tailscale",
        ))

    # Check TUN via HostConfig attrs — no subprocess/docker exec needed
    if userspace == "false":
        host_cfg = ts.attrs.get("HostConfig", {}) or {}
        devices = host_cfg.get("Devices") or []
        has_tun = any("/dev/net/tun" in str(d.get("PathOnHost", "")) for d in devices)
        cap_add = host_cfg.get("CapAdd") or []
        has_net_admin = "NET_ADMIN" in cap_add
        has_net_raw = "NET_RAW" in cap_add
        if not has_tun or not has_net_admin or not has_net_raw:
            missing = []
            if not has_net_admin:
                missing.append("NET_ADMIN")
            if not has_net_raw:
                missing.append("NET_RAW")
            if not has_tun:
                missing.append("/dev/net/tun")
            out.append(HealthIssue(
                id="tailscale.no_tun", severity="warning", category="Network",
                title="Tailscale tunnel permissions missing",
                detail=("Tailscale needs NET_ADMIN, NET_RAW, and /dev/net/tun when "
                        f"TS_USERSPACE=false. Missing: {', '.join(missing)}."),
                fix_hint="Redeploy Tailscale",
            ))

    try:
        result = ts.exec_run("tailscale status --json", demux=False)
        exit_code = getattr(result, "exit_code", 1)
        output = getattr(result, "output", b"") or b""
        if exit_code != 0:
            out.append(HealthIssue(
                id="tailscale.status_unavailable", severity="warning", category="Network",
                title="Tailscale tunnel status unavailable",
                detail="The container is running, but `tailscale status` failed. It may be unauthenticated or disconnected.",
                fix_hint="Redeploy Tailscale",
            ))
        else:
            status = json.loads(output.decode("utf-8", errors="replace") or "{}")
            backend_state = str(status.get("BackendState") or "")
            self_state = status.get("Self") or {}
            tailscale_ips = self_state.get("TailscaleIPs") or []
            online = self_state.get("Online")
            if backend_state != "Running" or online is False or not tailscale_ips:
                out.append(HealthIssue(
                    id="tailscale.tunnel_down", severity="warning", category="Network",
                    title="Tailscale tunnel not connected",
                    detail="Tailscale is running, but no active connected tunnel/IP was reported.",
                    fix_hint="Redeploy Tailscale",
                ))
            ts_routes = (env.get("TS_ROUTES") or "").strip()
            if ts_routes and ts_routes not in ("${TS_ROUTES:-}", ""):
                active_routes = self_state.get("PrimaryRoutes") or self_state.get("AllowedIPs") or []
                if active_routes and not any(route in active_routes for route in ts_routes.split(",")):
                    out.append(HealthIssue(
                        id="tailscale.routes_inactive", severity="warning", category="Network",
                        title="Tailscale subnet route not active",
                        detail="TS_ROUTES is set, but the route is not reported active by Tailscale.",
                        fix_hint="Redeploy Tailscale",
                    ))
    except Exception as e:
        out.append(HealthIssue(
            id="tailscale.status_check_failed", severity="warning", category="Network",
            title="Tailscale tunnel check failed",
            detail=f"Could not verify active tunnel status: {e}",
            fix_hint="Redeploy Tailscale",
        ))
    return out


def check_cloudflare_tunnel(ctx: _CheckContext) -> list[HealthIssue]:
    cf = ctx.get("cloudflared")
    if not cf:
        return []

    out = []
    env = ctx.env_of("cloudflared")
    token = (env.get("TUNNEL_TOKEN") or env.get("CLOUDFLARED_TOKEN") or "").strip()
    if cf.status != "running":
        out.append(HealthIssue(
            id="cloudflared.not_running", severity="error", category="Network",
            title="Cloudflare Tunnel is not running",
            detail=f"Local cloudflared container state is '{cf.status}'. Public tunnel access is offline.",
            fix_hint="Redeploy Cloudflared",
            auto_fix_available=True,
        ))
        return out

    if not token or token in ("${CLOUDFLARED_TOKEN}", "${TUNNEL_TOKEN}"):
        out.append(HealthIssue(
            id="cloudflared.no_token", severity="error", category="Network",
            title="Cloudflare Tunnel token missing",
            detail="cloudflared is running locally, but no TUNNEL_TOKEN is configured.",
            fix_hint="Redeploy Cloudflared",
        ))

    try:
        logs = cf.logs(tail=200).decode("utf-8", errors="replace")
    except Exception as e:
        out.append(HealthIssue(
            id="cloudflared.logs_unavailable", severity="warning", category="Network",
            title="Cloudflare Tunnel status unknown",
            detail=f"cloudflared is running locally, but recent logs could not be read: {e}",
            fix_hint="Check Cloudflare Tunnel",
        ))
        return out

    tunnel_ids = sorted(set(re.findall(r"tunnel(?:ID|_id)=([a-f0-9-]{8,})", logs, flags=re.I)))
    name_or_id = env.get("TUNNEL_NAME") or env.get("CLOUDFLARED_TUNNEL_NAME") or (tunnel_ids[-1] if tunnel_ids else "")
    if not name_or_id:
        out.append(HealthIssue(
            id="cloudflared.name_unknown", severity="info", category="Network",
            title="Cloudflare tunnel name not visible locally",
            detail="cloudflared runs with a token, so RAD cannot read the tunnel name. Confirm the name in Cloudflare Zero Trust.",
            fix_hint="Check Cloudflare Tunnel",
        ))

    error_patterns = [
        (r"(invalid|rejected|expired|unauthorized|forbidden).*token|token.*(invalid|rejected|expired|unauthorized|forbidden)",
         "Cloudflare Tunnel token rejected",
         "Cloudflare rejected the tunnel token. Update the token from Zero Trust."),
        (r"unauthorized|forbidden",
         "Cloudflare Tunnel unauthorized",
         "Cloudflare rejected cloudflared authentication. Check the tunnel token in Zero Trust."),
        (r"certificate.*(error|failed|invalid)|authentication.*(error|failed)",
         "Cloudflare Tunnel certificate error",
         "cloudflared reported a certificate/authentication problem."),
    ]
    for pattern, title, detail in error_patterns:
        if re.search(pattern, logs, flags=re.I):
            out.append(HealthIssue(
                id=f"cloudflared.{title.lower().replace(' ', '_')}", severity="error", category="Network",
                title=title,
                detail=detail,
                fix_hint="Redeploy Cloudflared",
            ))
            return out

    connected = "Registered tunnel connection" in logs or "Connection registered" in logs
    if not connected:
        out.append(HealthIssue(
            id="cloudflared.not_connected", severity="warning", category="Network",
            title="Cloudflare Tunnel not connected",
            detail="cloudflared is running locally, but no active Cloudflare edge connection appears in recent logs.",
            fix_hint="Check Cloudflare Tunnel",
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


def check_tinyauth(ctx: _CheckContext) -> list[HealthIssue]:
    """Verify Tinyauth is running and all Traefik routers have the two-router pattern.

    When Tinyauth is in the stack, every web service should have both:
      - A <name>-lan router (LAN bypass, no middleware)
      - A <name> router (Tinyauth ForwardAuth middleware)

    If a service only has the plain router and is missing the -lan variant,
    LAN users will also be challenged — not necessarily a security hole but
    almost certainly unintentional.

    If a service has neither router at all it may not have Traefik labels,
    which we don't flag here (cf_video_streaming check handles Plex/Jellyfin).
    """
    tinyauth = ctx.get("tinyauth")
    if not tinyauth:
        return []  # not in stack, nothing to check

    out = []

    if tinyauth.status != "running":
        out.append(HealthIssue(
            id="tinyauth.not_running", severity="error", category="auth",
            title="Tinyauth container is not running",
            detail=f"State: '{tinyauth.status}'. Auth is broken — all Tailscale access is ungated.",
            fix_hint="docker start tinyauth",
            auto_fix_available=True,
        ))
        return out  # remaining checks meaningless if not running

    # Check env vars are set
    env = ctx.env_of("tinyauth")
    # v5 env var names — SECRET removed, now uses SQLite sessions
    missing_vars = []
    for var in ("TINYAUTH_APPURL", "TINYAUTH_AUTH_USERS"):
        val = env.get(var, "").strip()
        if not val or val.startswith("${"):
            missing_vars.append(var)

    if missing_vars:
        out.append(HealthIssue(
            id="tinyauth.missing_env", severity="error", category="auth",
            title=f"Tinyauth missing required env vars: {', '.join(missing_vars)}",
            detail=("These variables must be set for Tinyauth to work. "
                    "USERS must contain at least one 'username:bcrypt_hash' entry."),
            fix_hint="Set the missing vars in your .env file and recreate the tinyauth container.",
        ))

    # Check running containers only — stopped containers have stale labels
    # from before Tinyauth was added and cause false positives.
    # Infrastructure services that are never behind Tinyauth are also skipped.
    SKIP_NAMES = {"tinyauth", "traefik", "cloudflared", "tailscale", "mediastack-rad"}
    plain_routers: set[str] = set()
    lan_routers:   set[str] = set()

    for c in ctx.running_containers:
        if c.name in SKIP_NAMES:
            continue
        labels = c.labels or {}
        for key in labels:
            if key.startswith("traefik.http.routers.") and key.endswith(".rule"):
                parts = key.split(".")
                if len(parts) >= 4:
                    router_name = parts[3]
                    if router_name.endswith("-lan"):
                        lan_routers.add(router_name[:-4])
                    else:
                        plain_routers.add(router_name)

    missing_lan = plain_routers - lan_routers
    for skip in SKIP_NAMES:
        missing_lan.discard(skip)

    for name in sorted(missing_lan):
        out.append(HealthIssue(
            id=f"tinyauth.missing_lan_router.{name}",
            severity="warning",
            category="auth",
            title=f"'{name}' missing LAN bypass router",
            detail=(f"Tinyauth is enabled but '{name}' only has a single Traefik router. "
                    "LAN users will be challenged for credentials when accessing this service. "
                    "Redeploy via Stack Builder to get the two-router pattern."),
            fix_hint="Regenerate and redeploy via Stack Builder with Tinyauth enabled.",
        ))

    return out


# ---------------------------------------------------------------------------
# Check metadata: function name → (category, label, ok_summary)
# Used by run_checks() to build per-check results for the Health tab.
# ---------------------------------------------------------------------------

CHECK_META: dict[str, tuple[str, str, str]] = {
    "check_docker_socket":    ("Docker",  "Docker daemon",        "connected"),
    "check_compose_file":     ("Config",  "Compose file",         "valid"),
    "check_env_file":         ("Config",  "Environment file",     "no issues"),
    "check_traefik_yaml":     ("Traefik", "Traefik.yml",          "valid"),
    "check_ghost_containers": ("Docker",  "Ghost containers",     "none found"),
    "check_port_conflicts":   ("Docker",  "Port conflicts",       "no conflicts"),
    "check_acme_storage":     ("Traefik", "ACME storage",         "mode 0600"),
    "check_traefik_network":  ("Traefik", "Service networks",     "all services connected"),
    "check_tailscale":        ("Network", "Tailscale",            "running"),
    "check_cloudflare_tunnel":("Network", "Cloudflare Tunnel",    "connected"),
    "check_tinyauth":         ("Auth",    "Tinyauth",             "running, all routers correct"),
    "check_cloudflare_token": ("Traefik", "Cloudflare token",     "valid"),
}


SYNC_CHECKS: list[Callable[[_CheckContext], list[HealthIssue]]] = [
    check_docker_socket,
    check_compose_file,
    check_env_file,
    check_traefik_yaml,
    check_ghost_containers,
    check_port_conflicts,
    check_acme_storage,
    check_traefik_network,
    check_tailscale,
    check_cloudflare_tunnel,
    check_tinyauth,
]

ASYNC_CHECKS = [check_cloudflare_token]


def _issues_to_checks(
    func_name: str,
    issues: list[HealthIssue],
) -> list[CheckResult]:
    """Convert a check function's output to CheckResult rows.

    No issues → one green row with the ok summary.
    One or more issues → one row per issue (each can be expanded/fixed).
    """
    meta = CHECK_META.get(func_name)
    category = meta[0] if meta else "System"
    label    = meta[1] if meta else func_name
    ok_msg   = meta[2] if meta else "passed"

    if not issues:
        return [CheckResult(
            id=f"{func_name}.ok",
            category=category, label=label,
            status="ok", summary=ok_msg,
        )]

    results = []
    for issue in issues:
        results.append(CheckResult(
            id=issue.id,
            category=issue.category or category,
            label=label,
            status="error" if issue.severity == "error" else "warning",
            summary=issue.title,
            detail=issue.detail,
            fix_hint=issue.fix_hint,
            auto_fix_available=issue.auto_fix_available,
        ))
    return results


async def run_checks() -> HealthReport:
    start = time.monotonic()
    all_checks: list[CheckResult] = []
    all_issues: list[HealthIssue] = []

    ctx = _CheckContext.fetch()

    for check in SYNC_CHECKS:
        try:
            issues = check(ctx)
            all_issues.extend(issues)
            all_checks.extend(_issues_to_checks(check.__name__, issues))
        except Exception as e:
            logger.exception("Check %s failed", check.__name__)
            crash_issue = HealthIssue(
                id=f"check.crash.{check.__name__}", severity="warning",
                category="internal",
                title=f"Check '{check.__name__}' crashed", detail=str(e),
            )
            all_issues.append(crash_issue)
            all_checks.extend(_issues_to_checks(check.__name__, [crash_issue]))

    async def _run_async(check):
        try:
            return await asyncio.wait_for(check(ctx), timeout=8.0)
        except asyncio.TimeoutError:
            return [HealthIssue(
                id=f"check.timeout.{check.__name__}", severity="warning",
                category="network",
                title=f"Check '{check.__name__}' timed out (>8s)",
                detail="Network call did not complete. Check connectivity.",
            )]
        except Exception as e:
            logger.exception("Async check %s failed", check.__name__)
            return []

    async_results = await asyncio.gather(*[_run_async(c) for c in ASYNC_CHECKS])
    for i, issues in enumerate(async_results):
        all_issues.extend(issues)
        func_name = ASYNC_CHECKS[i].__name__ if i < len(ASYNC_CHECKS) else "async_check"
        all_checks.extend(_issues_to_checks(func_name, issues))

    summary: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for i in all_issues:
        summary[i.severity] = summary.get(i.severity, 0) + 1

    return HealthReport(
        ok=(summary["error"] == 0),
        checked_at=time.time(),
        duration_ms=int((time.monotonic() - start) * 1000),
        checks=all_checks,
        issues=all_issues,
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
    if issue_id == "tinyauth.not_running":
        try:
            docker_client.start("tinyauth")
            return True, "Started tinyauth"
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

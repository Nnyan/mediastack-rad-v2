"""Pydantic schemas used across the HTTP and WebSocket APIs.

Keeping all schemas in one place makes the API surface easy to audit
and keeps frontend/backend in sync when models change.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Container models
# ---------------------------------------------------------------------------


class ContainerPort(BaseModel):
    """A single exposed port mapping on a container."""
    host_port: int | None = None
    container_port: int
    protocol: Literal["tcp", "udp"] = "tcp"


class ContainerSummary(BaseModel):
    """Lightweight container info shown in the dashboard list view."""
    id: str
    name: str
    image: str
    status: str  # running, exited, paused, etc.
    state: str   # docker state enum
    health: str  # healthy, unhealthy, starting, none
    created: int  # unix timestamp
    ports: list[ContainerPort] = []
    labels: dict[str, str] = {}
    networks: list[str] = []


class ContainerStats(BaseModel):
    """Live CPU / memory / network stats for a container."""
    id: str
    name: str
    cpu_percent: float
    mem_usage_bytes: int
    mem_limit_bytes: int
    mem_percent: float
    net_rx_bytes: int
    net_tx_bytes: int


# ---------------------------------------------------------------------------
# Stack builder models
# ---------------------------------------------------------------------------


class ServiceChoice(BaseModel):
    """A service the user has selected to include in the generated stack."""
    key: str  # matches catalog entry
    enabled: bool = True
    config: dict[str, Any] = {}  # arbitrary overrides (ports, volumes)


class StackRequest(BaseModel):
    """Payload for generating or deploying a full stack."""
    domain: str | None = None  # e.g. nyrdalyrt.com
    cert_resolver: str = "letsencrypt"  # traefik resolver name
    puid: int = 1000
    pgid: int = 1000
    timezone: str = "UTC"
    media_root: str = "/mnt/media"
    config_root: str = "/home/stack/mediacenter/config"
    cloudflare_token: str | None = None  # CF_DNS_API_TOKEN for DNS-01
    services: list[ServiceChoice] = []
    external_plex_url: str | None = None  # if user has Plex elsewhere
    # Tailscale
    tailscale_auth_key: str | None = None  # TS_AUTHKEY — reusable key from admin console
    tailscale_routes: str | None = None    # TS_ROUTES — subnet CIDR to advertise
    tailscale_hostname: str = "mediastack" # how node appears in Tailscale admin


# ---------------------------------------------------------------------------
# Health / checklist models
# ---------------------------------------------------------------------------


class HealthIssue(BaseModel):
    """A single problem the health checker found.

    `severity=error` means something is broken and must be fixed.
    `severity=warning` means it's suspicious but might be intentional.
    `severity=info` is for setup reminders (not broken, just incomplete).
    """
    id: str  # stable identifier for dismissal/acknowledgment
    severity: Literal["error", "warning", "info"]
    category: str  # "docker", "traefik", "network", "security", "config"
    title: str
    detail: str
    fix_hint: str | None = None  # optional one-line suggested fix
    auto_fix_available: bool = False


class HealthReport(BaseModel):
    """Complete output of a health checker pass."""
    ok: bool  # True if no errors (warnings don't count)
    checked_at: float  # unix timestamp
    duration_ms: int
    issues: list[HealthIssue]
    summary: dict[str, int]  # counts by severity


class ChecklistItem(BaseModel):
    """An actionable setup step shown in the UI checklist."""
    id: str
    title: str
    detail: str
    done: bool
    category: str  # "essential", "recommended", "optional"
    action_url: str | None = None  # deep link into RAD or external doc

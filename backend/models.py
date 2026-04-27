"""Pydantic schemas used across the HTTP and WebSocket APIs.

Keeping all schemas in one place makes the API surface easy to audit
and keeps frontend/backend in sync when models change.
"""
from __future__ import annotations

from typing import Literal
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
    web_url: str | None = None


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
    key: str                           # matches catalog entry
    enabled: bool = True
    port_override: int | None = None   # override the host-side port only
                                       # (Traefik still routes to the internal port)
    extra_env: dict[str, str] = {}     # arbitrary env vars merged in last,
                                       # after catalog defaults and request values


class StackRequest(BaseModel):
    """Payload for generating or deploying a full stack."""
    domain: str | None = None          # e.g. nyrdalyrt.com
    cert_resolver: str = "letsencrypt" # traefik resolver name
    puid: int = 1000
    pgid: int = 1000
    timezone: str = "UTC"
    media_root: str = "/mnt/media"
    config_root: str = "/home/stack/mediacenter/config"
    cloudflare_token: str | None = None         # CF_DNS_API_TOKEN for DNS-01
    cloudflare_tunnel_token: str | None = None  # TUNNEL_TOKEN for cloudflared
    plex_claim: str | None = None               # PLEX_CLAIM — required for first boot
    plex_server_name: str | None = None         # friendly server name shown in Plex clients
    plex_token: str | None = None               # X-Plex-Token — used by *arr apps to auth with Plex
    plex_url: str | None = None                 # Plex server URL for existing servers (overrides external_plex_url)
    services: list[ServiceChoice] = []
    external_plex_url: str | None = None  # if user has Plex elsewhere (legacy, use plex_url)
    # Tailscale
    tailscale_auth_key: str | None = None   # TS_AUTHKEY — reusable key from admin console
    tailscale_routes: str | None = None     # TS_ROUTES — subnet CIDR to advertise
    tailscale_hostname: str = "mediastack"  # how node appears in Tailscale admin
    # Egress VPN / Gluetun — generic WireGuard/OpenVPN configuration
    vpn_service_provider: str | None = None
    vpn_type: Literal["wireguard", "openvpn"] = "wireguard"
    wireguard_private_key: str | None = None
    wireguard_addresses: str | None = None
    openvpn_user: str | None = None
    openvpn_password: str | None = None
    wireguard_config: str | None = None
    server_countries: str | None = None
    server_region: str | None = None
    server_cities: str | None = None
    secure_core_only: bool | None = None
    stream_only: bool | None = None
    port_forward_only: bool | None = None
    # Tinyauth — Traefik ForwardAuth for Tailscale / non-LAN access
    tinyauth_enabled: bool = False
    # v5 env vars — SECRET removed (v5 uses SQLite sessions, no cookie secret)
    tinyauth_users: str | None = None       # TINYAUTH_AUTH_USERS: "user:bcrypt_hash"
    tinyauth_app_url: str | None = None     # TINYAUTH_APPURL: e.g. https://auth.nyrdalyrt.com
    lan_subnet: str = "10.0.0.0/22"        # this subnet bypasses Tinyauth entirely
    custom_yaml: str | None = None         # raw compose YAML fragment to merge


# ---------------------------------------------------------------------------
# Stack validation models
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """A single problem found during pre-generation validation."""
    service: str | None = None   # None = request-level issue
    field: str | None = None
    severity: Literal["error", "warning"]
    message: str


class PortConflict(BaseModel):
    """A port clash between a requested service and a currently running container."""
    service: str          # catalog key of the requesting service
    port: int             # the conflicting host port
    conflict_with: str    # name of the container currently holding the port
    suggested_port: int   # next available port we recommend


class StackValidation(BaseModel):
    """Result of pre-generation validation: conflicts + missing fields."""
    valid: bool
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    port_conflicts: list[PortConflict] = []


# ---------------------------------------------------------------------------
# Health / checklist models
# ---------------------------------------------------------------------------


class CheckResult(BaseModel):
    """Result of a single named health check — shown in the Health tab."""
    id: str                         # stable identifier
    category: str                   # grouping label: Docker / Config / Traefik / Auth
    label: str                      # human-readable check name
    status: Literal["ok", "warning", "error"]
    summary: str                    # one-line result for the row
    detail: str | None = None       # expanded text shown on click
    fix_hint: str | None = None
    auto_fix_available: bool = False


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
    ok: bool
    checked_at: float
    duration_ms: int
    checks: list[CheckResult] = []   # every check run — pass and fail
    issues: list[HealthIssue] = []   # issues only (subset of checks, kept for compat)
    summary: dict[str, int]


class ChecklistItem(BaseModel):
    """An actionable setup step shown in the UI checklist."""
    id: str
    title: str
    detail: str
    done: bool
    category: str  # "essential", "recommended", "optional"
    action_url: str | None = None  # deep link into RAD or external doc


# ---------------------------------------------------------------------------
# Settings / Secrets models
# ---------------------------------------------------------------------------


class SecretEntry(BaseModel):
    """A single secret shown in the Settings → Secrets panel."""
    key: str            # env var name, e.g. CF_DNS_API_TOKEN
    label: str          # human-readable label
    hint: str           # one-line description
    service: str        # which service needs this, e.g. "cloudflared"
    is_set: bool        # True if the key has a non-empty value in .env
    link: str | None = None   # optional doc/dashboard URL
    masked_value: str | None = None  # masked value preview, e.g. ********


class SecretValue(BaseModel):
    """A secret value returned for explicit reveal in the Settings panel."""
    key: str
    value: str

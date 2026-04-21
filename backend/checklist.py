"""Setup checklist — shows only incomplete setup steps.

Performance:
  - 20s result cache so the polling frontend never triggers expensive work
  - All container state fetched once via containers.list() and indexed by name
    (previously 11 separate Docker API calls per build)
  - _traefik_routers() is cached inside the same TTL window and has a hard 2s
    timeout so a down Traefik never blocks for 4s (2s + 2s fallback)
  - build_checklist() returns only incomplete items — done items are filtered
    before caching so the frontend payload stays small
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Optional

import yaml

from . import docker_client
from .config import config
from .models import ChecklistItem

logger = logging.getLogger(__name__)

_cache_ttl = 20.0
_cache_time: float = 0.0
_cache_items: list[ChecklistItem] = []

# Separate cache for Traefik routers (HTTP call)
_routers_cache_time: float = 0.0
_routers_cache: dict = {}


# ---------------------------------------------------------------------------
# Helpers — all use the pre-fetched by_name dict, never hit Docker again
# ---------------------------------------------------------------------------

def _fetch_containers() -> dict[str, object]:
    """Return all containers indexed by name. One Docker API call."""
    try:
        containers = docker_client.client().containers.list(all=True)
        return {c.name: c for c in containers}
    except Exception as e:
        logger.warning("checklist: cannot list containers: %s", e)
        return {}


def _is_running(by_name: dict, name: str) -> bool:
    c = by_name.get(name)
    return bool(c and c.status == "running")


def _env_of(by_name: dict, name: str) -> dict[str, str]:
    c = by_name.get(name)
    if not c:
        return {}
    result = {}
    for entry in (c.attrs.get("Config", {}).get("Env", []) or []):
        if "=" in entry:
            k, _, v = entry.partition("=")
            result[k] = v  # last wins (Docker behaviour)
    return result


def _labels_of(by_name: dict, name: str) -> dict[str, str]:
    c = by_name.get(name)
    if not c:
        return {}
    return c.attrs.get("Config", {}).get("Labels") or {}


def _traefik_routers() -> dict[str, dict]:
    """Fetch Traefik routers with caching. Hard 2s timeout — never blocks."""
    global _routers_cache_time, _routers_cache
    now = time.monotonic()
    if now - _routers_cache_time < _cache_ttl:
        return _routers_cache

    for url in ("http://traefik:8081/api/http/routers",
                "http://localhost:8081/api/http/routers"):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                data = json.loads(r.read())
                _routers_cache = {item["name"]: item for item in data}
                _routers_cache_time = now
                return _routers_cache
        except Exception:
            continue

    return _routers_cache  # return stale on failure rather than {}


def _service_has_route(service_name: str, routers: dict) -> bool:
    r = routers.get(f"{service_name}@docker")
    return bool(r and r.get("status") == "enabled")


def _traefik_yaml_has_cf() -> bool:
    t = config.traefik_dir / "traefik.yml"
    if not t.exists():
        return False
    try:
        doc = yaml.safe_load(t.read_text()) or {}
        for r in (doc.get("certificatesResolvers") or {}).values():
            dns = ((r or {}).get("acme", {}).get("dnsChallenge") or {})
            if dns.get("provider") == "cloudflare":
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_checklist() -> list[ChecklistItem]:
    """Return only incomplete checklist items, from cache when fresh."""
    global _cache_time, _cache_items
    now = time.monotonic()
    if now - _cache_time < _cache_ttl:
        return _cache_items

    all_items = _build()
    _cache_items = [i for i in all_items if not i.done]
    _cache_time = now
    return _cache_items


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _build() -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    # Single Docker call — all helpers below use this dict
    by_name = _fetch_containers()
    routers = _traefik_routers()

    # Parse compose file for service list
    compose_file = config.stack_dir / "docker-compose.yml"
    services: dict = {}
    if compose_file.exists():
        try:
            compose = yaml.safe_load(compose_file.read_text()) or {}
            services = compose.get("services") or {}
        except Exception:
            pass

    service_names = list(services.keys())

    # ---- Essential --------------------------------------------------------

    items.append(ChecklistItem(
        id="compose.generated",
        title="Generate your docker-compose.yml",
        detail="Use the Stack Builder to pick services and click Deploy.",
        done=compose_file.exists() and bool(services),
        category="essential",
        action_url="/stack-builder",
    ))

    items.append(ChecklistItem(
        id="containers.running",
        title="Bring the stack up",
        detail="After generating the compose file, deploy it from the Stack Builder.",
        done=any(_is_running(by_name, n) for n in service_names) or _is_running(by_name, "traefik"),
        category="essential",
        action_url="/stack-builder",
    ))

    items.append(ChecklistItem(
        id="traefik.config",
        title="Configure Traefik for HTTPS",
        detail="Set your domain and email so Let's Encrypt can issue certs via Cloudflare DNS-01.",
        done=_traefik_yaml_has_cf(),
        category="essential",
        action_url="/traefik",
    ))

    traefik_env = _env_of(by_name, "traefik")
    cf_token = traefik_env.get("CF_DNS_API_TOKEN", "").strip()
    items.append(ChecklistItem(
        id="traefik.cf_token",
        title="Set the Cloudflare API token on Traefik",
        detail=(
            "Token needs Zone:DNS:Edit + Zone:Zone:Read. "
            "Check for duplicate CF_DNS_API_TOKEN lines — the last one wins silently."
        ),
        done=bool(cf_token),
        category="essential",
        action_url="/traefik",
    ))

    # External access
    cf_env = _env_of(by_name, "cloudflared")
    cloudflared_running = _is_running(by_name, "cloudflared")
    cf_tunnel_token = cf_env.get("TUNNEL_TOKEN", "")
    cloudflared_ok = cloudflared_running and bool(
        cf_tunnel_token and cf_tunnel_token not in ("${CLOUDFLARED_TOKEN}", "")
    )
    has_live_routes = any(_service_has_route(s, routers) for s in service_names)

    if cloudflared_ok:
        web_services = [
            n for n, svc in services.items()
            if isinstance(svc, dict) and
            any("traefik.enable=true" in str(l) for l in (svc.get("labels") or []))
        ]
        unrouted = [s for s in web_services if not _service_has_route(s, routers)]
        if unrouted:
            items.append(ChecklistItem(
                id="tunnel.hostnames",
                title=f"Add Tunnel hostnames for: {', '.join(unrouted)}",
                detail=(
                    "Cloudflared is running but these services have no public hostname. "
                    "Go to Cloudflare Zero Trust → Networks → Tunnels → your tunnel → "
                    "Public Hostnames and add each one (e.g. sonarr → http://sonarr:8989)."
                ),
                done=False,
                category="essential",
                action_url="https://one.dash.cloudflare.com/",
            ))
        else:
            items.append(ChecklistItem(
                id="external.access",
                title="External access via Cloudflare Tunnel ✓",
                detail="Tunnel running and all services have registered routes.",
                done=True,
                category="essential",
            ))
    else:
        items.append(ChecklistItem(
            id="external.access",
            title="Configure external access",
            detail=(
                "Option A (recommended): Add cloudflared with a TUNNEL_TOKEN and configure "
                "public hostnames in Cloudflare Zero Trust. "
                "Option B: Forward ports 80 and 443 from your router and add DNS A records."
            ),
            done=has_live_routes,
            category="essential",
            action_url="https://one.dash.cloudflare.com/",
        ))

    # ---- Tailscale --------------------------------------------------------

    if "tailscale" in services:
        ts_env = _env_of(by_name, "tailscale")
        ts_running = _is_running(by_name, "tailscale")
        ts_authkey = ts_env.get("TS_AUTHKEY", "")
        ts_auth_set = bool(ts_authkey and ts_authkey != "${TS_AUTHKEY}")
        ts_routes = ts_env.get("TS_ROUTES", "")
        ts_routes_set = bool(ts_routes and ts_routes not in ("${TS_ROUTES:-}", ""))

        items.append(ChecklistItem(
            id="tailscale.running",
            title="Tailscale container is running",
            detail="Check logs with: docker logs tailscale",
            done=ts_running,
            category="essential",
            action_url="/containers",
        ))
        items.append(ChecklistItem(
            id="tailscale.authkey",
            title="Set your Tailscale auth key",
            detail=(
                "Generate a reusable, non-ephemeral key at "
                "https://login.tailscale.com/admin/settings/keys — "
                "select Reusable and optionally tag as tag:server."
            ),
            done=ts_auth_set,
            category="essential",
            action_url="https://login.tailscale.com/admin/settings/keys",
        ))
        items.append(ChecklistItem(
            id="tailscale.routes",
            title="Configure subnet routes (recommended)",
            detail=(
                "Set TS_ROUTES to your Docker subnet (e.g. 172.20.0.0/16) so all containers "
                "are reachable from any tailnet device. Find your subnet: "
                "docker network inspect mediastack | grep Subnet"
            ),
            done=ts_routes_set,
            category="recommended",
            action_url="https://login.tailscale.com/admin/machines",
        ))
        items.append(ChecklistItem(
            id="tailscale.approve_routes",
            title="Approve subnet routes in Tailscale admin",
            detail=(
                "Go to https://login.tailscale.com/admin/machines → your mediastack node "
                "→ Edit route settings → enable your advertised subnet."
            ),
            done=False,
            category="recommended",
            action_url="https://login.tailscale.com/admin/machines",
        ))
        items.append(ChecklistItem(
            id="tailscale.magicdns",
            title="Enable MagicDNS for hostname access (optional)",
            detail=(
                "With MagicDNS enabled, reach your stack as 'mediastack' from any enrolled "
                "device instead of by IP. Configure at https://login.tailscale.com/admin/dns"
            ),
            done=False,
            category="optional",
            action_url="https://login.tailscale.com/admin/dns",
        ))

    # ---- Per-service ------------------------------------------------------

    if "plex" in services:
        # CF Tunnel warning — only when plex container is actually running here.
        # External Plex servers won't appear in by_name at all.
        plex_c = by_name.get("plex")
        if plex_c and plex_c.status == "running" and "cloudflared" in services:
            plex_labels = _labels_of(by_name, "plex")
            plex_has_traefik = plex_labels.get("traefik.enable") == "true"
            items.append(ChecklistItem(
                id="plex.cf_tunnel_warning",
                title="Plex must NOT route through Cloudflare Tunnel",
                detail=(
                    "Cloudflare ToS section 2.8 prohibits proxying video streams — "
                    "risks account suspension. The generator excludes Plex from Traefik "
                    "labels automatically. For remote access: use Tailscale (best), "
                    "Plex's built-in relay, or port-forward 32400."
                ),
                done=not plex_has_traefik,
                category="essential",
                action_url="/health",
            ))

        items.append(ChecklistItem(
            id="plex.claim",
            title="Claim your Plex server",
            detail=(
                "Get a 4-minute token at plex.tv/claim, set PLEX_CLAIM in Plex's "
                "environment, and restart. Complete within 4 minutes of first start."
            ),
            done=False,
            category="recommended",
            action_url="https://www.plex.tv/claim/",
        ))

    if "bazarr" in services:
        items.append(ChecklistItem(
            id="bazarr.linkage",
            title="Connect Bazarr to Sonarr/Radarr",
            detail="Bazarr → Settings → Providers. Use http://sonarr:8989 and http://radarr:7878.",
            done=False,
            category="recommended",
            action_url="/containers",
        ))

    if "prowlarr" in services:
        items.append(ChecklistItem(
            id="prowlarr.apps",
            title="Sync Prowlarr with your *arr apps",
            detail="Prowlarr → Settings → Apps. Add Sonarr, Radarr, etc.",
            done=False,
            category="recommended",
            action_url="/containers",
        ))

    if "overseerr" in services or "jellyseerr" in services:
        items.append(ChecklistItem(
            id="overseerr.setup",
            title="Run the Overseerr setup wizard",
            detail="Link Plex/Jellyfin, Sonarr, and Radarr using internal container URLs.",
            done=False,
            category="recommended",
        ))

    # ---- Tinyauth auth --------------------------------------------------------

    if "tinyauth" in services:
        ta = by_name.get("tinyauth")
        ta_running = ta is not None and ta.status == "running"
        ta_env = _env_of(by_name, "tinyauth")

        # 1. Container running
        items.append(ChecklistItem(
            id="tinyauth.running",
            title="Tinyauth container is running",
            detail="Tinyauth must be running for Tailscale/WAN access to be gated.",
            done=ta_running,
            category="essential",
            action_url="/containers",
        ))

        # 2. SECRET set
        secret = ta_env.get("SECRET", "").strip()
        secret_set = bool(secret) and not secret.startswith("${")
        items.append(ChecklistItem(
            id="tinyauth.secret",
            title="Generate and set TINYAUTH_SECRET",
            detail=(
                "A random secret signs session cookies. Generate one with: "
                "python3 -c \"import secrets; print(secrets.token_hex(32))\""
            ),
            done=secret_set,
            category="essential",
        ))

        # 3. USERS set
        users = ta_env.get("USERS", "").strip()
        users_set = bool(users) and not users.startswith("${") and ":" in users
        items.append(ChecklistItem(
            id="tinyauth.users",
            title="Set TINYAUTH_USERS with a bcrypt password hash",
            detail=(
                "USERS format: username:$2y$... (bcrypt hash). Generate a hash: "
                "docker run --rm ghcr.io/steveiliop56/tinyauth:latest generate-hash --password yourpassword"
            ),
            done=users_set,
            category="essential",
        ))

        # 4. APP_URL set
        app_url = ta_env.get("APP_URL", "").strip()
        app_url_set = bool(app_url) and not app_url.startswith("${") and app_url.startswith("https://")
        items.append(ChecklistItem(
            id="tinyauth.app_url",
            title="Set TINYAUTH_APP_URL to your domain",
            detail=(
                "APP_URL must be the HTTPS base URL for cookie scoping and post-login redirect, "
                "e.g. https://auth.nyrdalyrt.com or https://sonarr.nyrdalyrt.com"
            ),
            done=app_url_set,
            category="essential",
        ))

        # 5. TOTP (optional, only show if enabled)
        totp = ta_env.get("TOTP_ENABLED", "").strip().lower()
        if totp == "true":
            items.append(ChecklistItem(
                id="tinyauth.totp",
                title="Enrol your TOTP authenticator",
                detail=(
                    "TOTP_ENABLED=true is set. Visit the Tinyauth UI once, log in with your "
                    "password, and scan the QR code with Google Authenticator or Bitwarden."
                ),
                done=False,
                category="essential",
                action_url="/containers",
            ))

        # 6. Test from Tailscale
        items.append(ChecklistItem(
            id="tinyauth.test_tailscale",
            title="Verify Tinyauth gates Tailscale access",
            detail=(
                "From a Tailscale-enrolled device (not on LAN), visit one of your "
                "service URLs. You should be redirected to the Tinyauth login page."
            ),
            done=False,
            category="recommended",
        ))

        # 7. Test LAN bypass
        items.append(ChecklistItem(
            id="tinyauth.test_lan",
            title="Verify LAN access bypasses Tinyauth",
            detail=(
                "From your local network (10.0.0.0/22), visit the same URL. "
                "You should NOT see the Tinyauth login — the service loads directly."
            ),
            done=False,
            category="recommended",
        ))

    # ---- Security ---------------------------------------------------------

    acme = config.traefik_dir / "letsencrypt" / "acme.json"
    items.append(ChecklistItem(
        id="security.acme_perms",
        title="Verify acme.json is mode 0600",
        detail="Wrong permissions silently break cert renewal.",
        done=acme.exists() and (acme.stat().st_mode & 0o777) == 0o600,
        category="optional",
    ))

    items.append(ChecklistItem(
        id="security.backups",
        title="Back up config and acme.json",
        detail="Back up your config volumes and certificates off this host.",
        done=False,
        category="optional",
    ))

    return items

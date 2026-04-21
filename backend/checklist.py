"""Setup checklist — shows only incomplete setup steps.

Completed items are removed from the list entirely rather than shown
greyed out — you don't need to be reminded of things you've done.

Performance: the compose parse and Docker queries are cached for
20 seconds so the checklist endpoint stays fast even when called
frequently by the Vue polling loop.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import yaml

from . import docker_client
from .config import config
from .models import ChecklistItem

logger = logging.getLogger(__name__)

_cache_ttl = 20.0
_cache_time: float = 0.0
_cache_items: list[ChecklistItem] = []


def _running(name: str) -> bool:
    try:
        c = docker_client.get_container_safe(name)
        return bool(c and c.status == "running")
    except Exception:
        return False


def _traefik_routers() -> dict[str, dict]:
    try:
        import urllib.request, json
        with urllib.request.urlopen("http://traefik:8081/api/http/routers", timeout=2) as r:
            return {item["name"]: item for item in json.loads(r.read())}
    except Exception:
        try:
            import urllib.request, json
            with urllib.request.urlopen("http://localhost:8081/api/http/routers", timeout=2) as r:
                return {item["name"]: item for item in json.loads(r.read())}
        except Exception:
            return {}


def _service_has_route(service_name: str, routers: dict) -> bool:
    r = routers.get(f"{service_name}@docker")
    return bool(r and r.get("status") == "enabled")


def _cloudflared_token_set() -> bool:
    try:
        c = docker_client.get_container_safe("cloudflared")
        if not c:
            return False
        env_list = c.attrs.get("Config", {}).get("Env", []) or []
        for entry in env_list:
            if entry.startswith("TUNNEL_TOKEN="):
                val = entry.split("=", 1)[1].strip()
                return bool(val and val != "${CLOUDFLARED_TOKEN}")
        return False
    except Exception:
        return False


def _traefik_yaml_has_cf() -> bool:
    t = config.traefik_dir / "traefik.yml"
    if not t.exists():
        return False
    try:
        doc = yaml.safe_load(t.read_text()) or {}
        for r in (doc.get("certificatesResolvers") or {}).values():
            if ((r or {}).get("acme", {}).get("dnsChallenge") or {}).get("provider") == "cloudflare":
                return True
    except Exception:
        pass
    return False


def _cf_token_in_traefik() -> bool:
    try:
        c = docker_client.get_container_safe("traefik")
        if not c:
            return False
        seen = {}
        for entry in (c.attrs.get("Config", {}).get("Env", []) or []):
            if "=" in entry:
                k, _, v = entry.partition("=")
                seen[k] = v
        return bool(seen.get("CF_DNS_API_TOKEN", "").strip())
    except Exception:
        return False


def build_checklist() -> list[ChecklistItem]:
    global _cache_time, _cache_items
    now = time.monotonic()
    if now - _cache_time < _cache_ttl:
        return _cache_items
    all_items = _build()
    _cache_items = [i for i in all_items if not i.done]
    _cache_time = now
    return _cache_items


def _build() -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    compose_file = config.stack_dir / "docker-compose.yml"
    compose_exists = compose_file.exists()
    services: dict = {}
    if compose_exists:
        try:
            compose = yaml.safe_load(compose_file.read_text()) or {}
            services = compose.get("services") or {}
        except Exception:
            pass

    service_names = list(services.keys())
    routers = _traefik_routers()

    # ---- Essential --------------------------------------------------------

    items.append(ChecklistItem(
        id="compose.generated",
        title="Generate your docker-compose.yml",
        detail="Use the Stack Builder to pick services and click Deploy.",
        done=compose_exists and bool(services),
        category="essential",
        action_url="/stack-builder",
    ))

    items.append(ChecklistItem(
        id="containers.running",
        title="Bring the stack up",
        detail="After generating the compose file, deploy it from the Stack Builder.",
        done=any(_running(n) for n in service_names) or _running("traefik"),
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

    items.append(ChecklistItem(
        id="traefik.cf_token",
        title="Set the Cloudflare API token on Traefik",
        detail=(
            "Token needs Zone:DNS:Edit + Zone:Zone:Read. "
            "Check for duplicate CF_DNS_API_TOKEN lines — the last one wins silently."
        ),
        done=_cf_token_in_traefik(),
        category="essential",
        action_url="/traefik",
    ))

    # External access — detect which method is in use
    cloudflared_ok = _running("cloudflared") and _cloudflared_token_set()
    has_live_routes = any(_service_has_route(s, routers) for s in service_names)

    if cloudflared_ok:
        # Tunnel running — check each web service has a hostname
        web_services = [
            n for n, svc in services.items()
            if isinstance(svc, dict) and
            any("traefik.enable=true" in str(l)
                for l in (svc.get("labels") or []))
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
                "Option A (recommended): Add cloudflared to your stack with a TUNNEL_TOKEN "
                "and configure public hostnames in Cloudflare Zero Trust. "
                "Option B: Forward ports 80 and 443 from your router to this host "
                "and add DNS A records in Cloudflare."
            ),
            done=has_live_routes,
            category="essential",
            action_url="https://one.dash.cloudflare.com/",
        ))

    # ---- Per-service -------------------------------------------------------

    if "plex" in services:
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
            detail="Prowlarr → Settings → Apps. Add Sonarr, Radarr, etc. to sync indexers.",
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

    # ---- Security ---------------------------------------------------------

    acme = config.traefik_dir / "letsencrypt" / "acme.json"
    acme_ok = acme.exists() and (acme.stat().st_mode & 0o777) == 0o600
    items.append(ChecklistItem(
        id="security.acme_perms",
        title="Verify acme.json is mode 0600",
        detail="Wrong permissions silently break cert renewal.",
        done=acme_ok,
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

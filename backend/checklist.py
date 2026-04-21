"""Setup checklist — live view of what the user still needs to do.

Distinct from the health checker: health is about things being broken
(or likely to break). The checklist is about completing setup. A fresh
install has many items unchecked; a fully configured stack has them
all checked. Items disappear once complete; health issues persist
until dismissed.

Examples of checklist items:
  - Set a Plex claim token within 4 minutes of first start
  - Configure Bazarr with Sonarr/Radarr API keys
  - Point your router's 80/443 ports at this server OR configure
    Cloudflare Tunnel hostnames
  - Link Overseerr to Plex
  - Add indexers to Prowlarr
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from . import docker_client
from .config import config
from .models import ChecklistItem

logger = logging.getLogger(__name__)


def _running(name: str) -> bool:
    """True if a container with this name is currently running."""
    c = docker_client.get_container_safe(name)
    return bool(c and c.status == "running")


def build_checklist() -> list[ChecklistItem]:
    """Return the current checklist state.

    Rebuilt from scratch on every call — cheap, and keeps logic simple.
    The items are derived from the current running containers and
    on-disk config files, so as the user makes changes the list updates
    on the next poll.
    """
    items: list[ChecklistItem] = []

    compose_file = config.stack_dir / "docker-compose.yml"
    compose_exists = compose_file.exists()
    compose: dict = {}
    if compose_exists:
        try:
            compose = yaml.safe_load(compose_file.read_text()) or {}
        except yaml.YAMLError:
            pass

    services = (compose.get("services") or {}) if compose else {}

    # ---- Essential: base infrastructure --------------------------------

    items.append(ChecklistItem(
        id="compose.generated",
        title="Generate your docker-compose.yml",
        detail=(
            "Use the Stack Builder to pick which services you want. "
            "Every service you add here gets a config directory, "
            "network attachment, and Traefik labels automatically."
        ),
        done=compose_exists and bool(services),
        category="essential",
        action_url="/stack-builder",
    ))

    items.append(ChecklistItem(
        id="containers.running",
        title="Bring the stack up",
        detail=(
            "After generating the compose file, run "
            "`docker compose up -d` or click Deploy Stack on the builder."
        ),
        done=_running("traefik") or any(_running(n) for n in services),
        category="essential",
        action_url="/stack-builder",
    ))

    # ---- Traefik / HTTPS ----------------------------------------------

    traefik_yaml = config.traefik_dir / "traefik.yml"
    has_traefik_yaml = traefik_yaml.exists()
    items.append(ChecklistItem(
        id="traefik.config",
        title="Configure Traefik for HTTPS",
        detail=(
            "Set your domain and email in the Traefik tab so Let's "
            "Encrypt can issue certificates via DNS-01."
        ),
        done=has_traefik_yaml,
        category="essential",
        action_url="/traefik",
    ))

    if "traefik" in services:
        t_env = (services["traefik"].get("environment") or {})
        has_cf = bool(t_env.get("CF_DNS_API_TOKEN") or "${CF_DNS_API_TOKEN}")
        items.append(ChecklistItem(
            id="traefik.cf_token",
            title="Set the Cloudflare API token",
            detail=(
                "The token needs Zone:DNS:Edit + Zone:Zone:Read on your "
                "domain. Without it DNS-01 cannot issue certificates."
            ),
            done=has_cf,
            category="essential",
            action_url="/traefik",
        ))

    # ---- External access ----------------------------------------------

    cloudflared_running = _running("cloudflared")
    items.append(ChecklistItem(
        id="external.access",
        title="Choose how you'll expose services externally",
        detail=(
            "Either forward ports 80/443 from your router to this host, "
            "or configure Cloudflare Tunnel public hostnames. The tunnel "
            "is recommended — it hides your home IP and needs no port "
            "forwarding."
        ),
        done=cloudflared_running,
        category="essential",
        action_url="https://one.dash.cloudflare.com/",
    ))

    # ---- Service-specific items ---------------------------------------

    if "plex" in services:
        items.append(ChecklistItem(
            id="plex.claim",
            title="Claim your Plex server",
            detail=(
                "Visit https://www.plex.tv/claim/ to get a 4-minute "
                "claim token, then restart Plex with CLAIM set in its "
                "environment. If you miss the window, delete the config "
                "volume and try again."
            ),
            done=False,  # no way to detect claim state from the outside
            category="recommended",
            action_url="https://www.plex.tv/claim/",
        ))

    if "bazarr" in services:
        items.append(ChecklistItem(
            id="bazarr.linkage",
            title="Connect Bazarr to Sonarr/Radarr",
            detail=(
                "Open Bazarr and enter your Sonarr and Radarr API keys "
                "under Settings → Providers. Bazarr can't detect them "
                "automatically — it needs the key from each arr app."
            ),
            done=False,
            category="recommended",
            action_url="/containers",
        ))

    if "prowlarr" in services:
        items.append(ChecklistItem(
            id="prowlarr.apps",
            title="Add your apps to Prowlarr",
            detail=(
                "In Prowlarr, go to Settings → Apps and add Sonarr, "
                "Radarr, Lidarr, Readarr (whichever you installed). "
                "This is how indexers get synced automatically."
            ),
            done=False,
            category="recommended",
            action_url="/containers",
        ))

    if "overseerr" in services or "jellyseerr" in services:
        items.append(ChecklistItem(
            id="overseerr.setup",
            title="Run the Overseerr setup wizard",
            detail=(
                "On first launch, Overseerr walks you through linking "
                "Plex (or Jellyfin), Sonarr, and Radarr. Use the "
                "internal container names (e.g. http://sonarr:8989) "
                "for the URLs since they share the stack network."
            ),
            done=False,
            category="recommended",
        ))

    # ---- Security / hardening -----------------------------------------

    acme = config.traefik_dir / "letsencrypt" / "acme.json"
    items.append(ChecklistItem(
        id="security.acme_perms",
        title="Verify acme.json permissions",
        detail=(
            "Traefik requires acme.json to be mode 0600 and owned by "
            "root. Wrong permissions silently break cert renewal."
        ),
        done=acme.exists() and (acme.stat().st_mode & 0o777) == 0o600,
        category="optional",
    ))

    items.append(ChecklistItem(
        id="security.backups",
        title="Back up config and acme.json",
        detail=(
            "Your config volumes hold all your *arr history, Plex "
            "library metadata, indexers, and the issued certificates. "
            "Back up at least $CONFIG_ROOT and acme.json somewhere "
            "off this host."
        ),
        done=False,
        category="optional",
    ))

    return items

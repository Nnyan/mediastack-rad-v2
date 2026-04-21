"""Catalog of services that the stack builder knows how to generate.

Each entry describes the canonical compose fragment for a service,
plus Traefik labels, volumes, env vars, and dependencies. Kept in
Python (not JSON) so we can compute fields based on user input
(e.g. domain, PUID, timezone) without a separate templating layer.

Adding a new service is just appending an entry here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ServiceDef:
    """Declarative definition of one service in the catalog."""
    key: str
    display_name: str
    description: str
    image: str
    category: str  # "media", "downloaders", "indexers", "requests", "infra"
    # Port the service listens on inside the container — used for both
    # host port mapping and Traefik upstream routing.
    web_port: int | None = None
    # Additional ports (not primary web UI) that need host exposure.
    extra_ports: list[str] = field(default_factory=list)
    # Paths inside the container that need persistent storage.
    config_volumes: list[str] = field(default_factory=list)
    # Extra paths that should mount from the media root.
    media_volumes: list[str] = field(default_factory=list)
    # Static environment variables baked into the compose file.
    env: dict[str, str] = field(default_factory=dict)
    # Services that must be deployed for this one to work.
    depends_on: list[str] = field(default_factory=list)
    # Extra compose command override (rare).
    command: str | None = None
    # Label customizations (applied after default Traefik labels).
    extra_labels: list[str] = field(default_factory=list)
    # If True, skip Traefik labels entirely (used for infra services).
    skip_traefik: bool = False
    # Callback for producing the final service dict — set when a service
    # needs logic too complex for the declarative fields above.
    custom_render: Callable | None = None


CATALOG: dict[str, ServiceDef] = {
    # --------------------------- Media servers ---------------------------
    "plex": ServiceDef(
        key="plex",
        display_name="Plex Media Server",
        description="Stream your media library to any device",
        image="lscr.io/linuxserver/plex:latest",
        category="media",
        web_port=32400,
        config_volumes=["/config"],
        media_volumes=["/data"],
        env={"VERSION": "docker"},
    ),
    "jellyfin": ServiceDef(
        key="jellyfin",
        display_name="Jellyfin",
        description="Open-source media server, no subscriptions",
        image="lscr.io/linuxserver/jellyfin:latest",
        category="media",
        web_port=8096,
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    # ------------------------------ *arr ---------------------------------
    "sonarr": ServiceDef(
        key="sonarr",
        display_name="Sonarr",
        description="TV show collection manager",
        image="lscr.io/linuxserver/sonarr:latest",
        category="indexers",
        web_port=8989,
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    "radarr": ServiceDef(
        key="radarr",
        display_name="Radarr",
        description="Movie collection manager",
        image="lscr.io/linuxserver/radarr:latest",
        category="indexers",
        web_port=7878,
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    "lidarr": ServiceDef(
        key="lidarr",
        display_name="Lidarr",
        description="Music collection manager",
        image="lscr.io/linuxserver/lidarr:latest",
        category="indexers",
        web_port=8686,
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    "readarr": ServiceDef(
        key="readarr",
        display_name="Readarr",
        # Note: the :develop tag lacks amd64 builds — we saw this bug
        # during setup. Use :latest to avoid platform mismatch errors.
        description="Book/audiobook collection manager",
        image="lscr.io/linuxserver/readarr:latest",
        category="indexers",
        web_port=8787,
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    "bazarr": ServiceDef(
        key="bazarr",
        display_name="Bazarr",
        description="Subtitle manager for Sonarr/Radarr",
        image="lscr.io/linuxserver/bazarr:latest",
        category="indexers",
        web_port=6767,
        config_volumes=["/config"],
        media_volumes=["/data"],
        depends_on=[],  # optional linkage — users set API keys manually
    ),
    "prowlarr": ServiceDef(
        key="prowlarr",
        display_name="Prowlarr",
        description="Indexer manager for the *arr apps",
        image="lscr.io/linuxserver/prowlarr:latest",
        category="indexers",
        web_port=9696,
        config_volumes=["/config"],
    ),
    # --------------------------- Downloaders -----------------------------
    "qbittorrent": ServiceDef(
        key="qbittorrent",
        display_name="qBittorrent",
        description="BitTorrent client with a web UI",
        image="lscr.io/linuxserver/qbittorrent:latest",
        category="downloaders",
        web_port=8080,
        extra_ports=["6881:6881", "6881:6881/udp"],
        config_volumes=["/config"],
        media_volumes=["/data"],
        env={"WEBUI_PORT": "8080"},
    ),
    "sabnzbd": ServiceDef(
        key="sabnzbd",
        display_name="SABnzbd",
        description="Usenet binary newsreader",
        image="lscr.io/linuxserver/sabnzbd:latest",
        category="downloaders",
        web_port=8080,  # remapped below via extra_ports to avoid clash
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    "nzbget": ServiceDef(
        key="nzbget",
        display_name="NZBGet",
        description="Lightweight Usenet downloader",
        image="lscr.io/linuxserver/nzbget:latest",
        category="downloaders",
        web_port=6789,
        config_volumes=["/config"],
        media_volumes=["/data"],
    ),
    # ----------------------------- Requests ------------------------------
    "overseerr": ServiceDef(
        key="overseerr",
        display_name="Overseerr",
        description="Media request and discovery for Plex",
        image="lscr.io/linuxserver/overseerr:latest",
        category="requests",
        web_port=5055,
        config_volumes=["/config"],
    ),
    "jellyseerr": ServiceDef(
        key="jellyseerr",
        display_name="Jellyseerr",
        description="Overseerr fork for Jellyfin",
        image="fallenbagel/jellyseerr:latest",
        category="requests",
        web_port=5055,
        config_volumes=["/app/config"],
    ),
    # ---------------------------- Infrastructure -------------------------
    "traefik": ServiceDef(
        key="traefik",
        display_name="Traefik",
        description="Reverse proxy with automatic HTTPS",
        image="traefik:latest",
        category="infra",
        web_port=8081,
        extra_ports=["80:80", "443:443"],
        # Traefik itself mounts the shared traefik dir + docker socket.
        # Those are added by the generator, not here.
        skip_traefik=False,
    ),
    "cloudflared": ServiceDef(
        key="cloudflared",
        display_name="Cloudflare Tunnel",
        description="Expose services without port forwarding",
        image="cloudflare/cloudflared:latest",
        category="infra",
        # cloudflared has no web UI of its own so it skips Traefik.
        skip_traefik=True,
        # The tunnel token is set via env var. Command must be explicit —
        # the default ENTRYPOINT isn't enough.
        command="tunnel --no-autoupdate run",
        env={"TUNNEL_TOKEN": "${CLOUDFLARED_TOKEN}"},
    ),
}


def services_in_category(category: str) -> list[ServiceDef]:
    """Return all catalog entries in the given category, stable order."""
    return sorted(
        (s for s in CATALOG.values() if s.category == category),
        key=lambda s: s.display_name.lower(),
    )


def get(key: str) -> ServiceDef | None:
    """Look up a service by its catalog key."""
    return CATALOG.get(key)

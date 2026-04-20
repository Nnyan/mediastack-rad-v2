"""
Compose file generator — builds a complete docker-compose.yml from
selected service definitions and optionally deploys it immediately.
"""

import os
import shutil
import subprocess
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
from ruamel.yaml.comments import CommentedMap, CommentedSeq

COMPOSE_DIR = "/compose"
OUTPUT_FILE = os.path.join(COMPOSE_DIR, "docker-compose.yml")

# ── Known service definitions ─────────────────────────────────────────────────
# Each entry describes a well-known mediastack service.
# These mirror the SERVICE_DEFINITIONS in the frontend's services.ts.

BASE_DATA = "/opt/mediastack"
MEDIA_PATH = "/mnt/media"
NETWORK = "mediastack"

SERVICE_CATALOG: dict[str, dict[str, Any]] = {
    # ── Infrastructure ──
    "traefik": {
        "image": "traefik:v3.1",
        "category": "infrastructure",
        "description": "Reverse proxy and load balancer with automatic TLS",
        "ports": ["80:80", "443:443", "8081:8081"],
        "volumes": [
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            f"{BASE_DATA}/traefik/letsencrypt:/letsencrypt",
            f"{BASE_DATA}/traefik/config:/etc/traefik",
        ],
        "environment": {
            "TRAEFIK_API_DASHBOARD": "true",
            "TRAEFIK_ENTRYPOINTS_WEB_ADDRESS": ":80",
            "TRAEFIK_ENTRYPOINTS_WEBSECURE_ADDRESS": ":443",
            "TRAEFIK_PROVIDERS_DOCKER": "true",
            "TRAEFIK_PROVIDERS_DOCKER_EXPOSEDBYDEFAULT": "false",
            "TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPT_ACME_EMAIL": "admin@example.com",
            "TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPT_ACME_STORAGE": "/letsencrypt/acme.json",
            "TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPT_ACME_HTTPCHALLENGE_ENTRYPOINT": "web",
        },
        "restart": "always",
        "depends_on": [],
    },
    "cloudflared": {
        "image": "cloudflare/cloudflared:latest",
        "category": "infrastructure",
        "description": "Cloudflare Tunnel — expose services without opening ports",
        "ports": [],
        "volumes": [f"{BASE_DATA}/cloudflared:/etc/cloudflared"],
        "environment": {
            "TUNNEL_TOKEN": "",
            "TUNNEL_TRANSPORT_PROTOCOL": "quic",
        },
        "restart": "always",
        "depends_on": [],
    },
    # ── Media ──
    "plex": {
        "image": "linuxserver/plex:latest",
        "category": "media",
        "description": "Plex Media Server",
        "ports": ["32400:32400"],
        "volumes": [
            f"{BASE_DATA}/plex/config:/config",
            f"{BASE_DATA}/plex/transcode:/transcode",
            f"{MEDIA_PATH}/movies:/movies",
            f"{MEDIA_PATH}/tv:/tv",
            f"{MEDIA_PATH}/music:/music",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
            "VERSION": "docker",
            "PLEX_CLAIM": "",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    "jellyfin": {
        "image": "linuxserver/jellyfin:latest",
        "category": "media",
        "description": "Free and open source media server",
        "ports": ["8096:8096"],
        "volumes": [
            f"{BASE_DATA}/jellyfin/config:/config",
            f"{MEDIA_PATH}/movies:/movies",
            f"{MEDIA_PATH}/tv:/tv",
            f"{MEDIA_PATH}/music:/music",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    # ── Management ──
    "sonarr": {
        "image": "linuxserver/sonarr:latest",
        "category": "management",
        "description": "TV series PVR — monitors and downloads episodes automatically",
        "ports": ["8989:8989"],
        "volumes": [
            f"{BASE_DATA}/sonarr/config:/config",
            f"{MEDIA_PATH}/tv:/tv",
            f"{MEDIA_PATH}/downloads:/downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": ["prowlarr"],
    },
    "radarr": {
        "image": "linuxserver/radarr:latest",
        "category": "management",
        "description": "Movie collection manager",
        "ports": ["7878:7878"],
        "volumes": [
            f"{BASE_DATA}/radarr/config:/config",
            f"{MEDIA_PATH}/movies:/movies",
            f"{MEDIA_PATH}/downloads:/downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": ["prowlarr"],
    },
    "lidarr": {
        "image": "linuxserver/lidarr:latest",
        "category": "management",
        "description": "Music collection manager",
        "ports": ["8686:8686"],
        "volumes": [
            f"{BASE_DATA}/lidarr/config:/config",
            f"{MEDIA_PATH}/music:/music",
            f"{MEDIA_PATH}/downloads:/downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": ["prowlarr"],
    },
    "readarr": {
        "image": "linuxserver/readarr:latest",
        "category": "management",
        "description": "Book collection manager",
        "ports": ["8787:8787"],
        "volumes": [
            f"{BASE_DATA}/readarr/config:/config",
            f"{MEDIA_PATH}/books:/books",
            f"{MEDIA_PATH}/downloads:/downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": ["prowlarr"],
    },
    "prowlarr": {
        "image": "linuxserver/prowlarr:latest",
        "category": "management",
        "description": "Unified indexer manager for all *arr apps",
        "ports": ["9696:9696"],
        "volumes": [
            f"{BASE_DATA}/prowlarr/config:/config",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    "bazarr": {
        "image": "linuxserver/bazarr:latest",
        "category": "management",
        "description": "Subtitle downloader for Sonarr and Radarr",
        "ports": ["6767:6767"],
        "volumes": [
            f"{BASE_DATA}/bazarr/config:/config",
            f"{MEDIA_PATH}/movies:/movies",
            f"{MEDIA_PATH}/tv:/tv",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": ["sonarr", "radarr"],
    },
    "overseerr": {
        "image": "sctx/overseerr:latest",
        "category": "management",
        "description": "Media request and discovery tool",
        "ports": ["5055:5055"],
        "volumes": [
            f"{BASE_DATA}/overseerr/config:/app/config",
        ],
        "environment": {
            "TZ": "UTC",
            "LOG_LEVEL": "info",
        },
        "restart": "unless-stopped",
        "depends_on": ["plex", "sonarr", "radarr"],
    },
    "flaresolverr": {
        "image": "ghcr.io/flaresolverr/flaresolverr:latest",
        "category": "management",
        "description": "Proxy server to bypass Cloudflare protection",
        "ports": ["8191:8191"],
        "volumes": [],
        "environment": {
            "LOG_LEVEL": "info",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    # ── Download clients ──
    "qbittorrent": {
        "image": "linuxserver/qbittorrent:latest",
        "category": "download",
        "description": "BitTorrent client with web UI",
        "ports": ["8080:8080", "6881:6881", "6881:6881/udp"],
        "volumes": [
            f"{BASE_DATA}/qbittorrent/config:/config",
            f"{MEDIA_PATH}/downloads/torrents:/downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
            "WEBUI_PORT": "8080",
            "TORRENTING_PORT": "6881",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    "sabnzbd": {
        "image": "linuxserver/sabnzbd:latest",
        "category": "download",
        "description": "Usenet binary newsreader",
        "ports": ["8085:8080"],
        "volumes": [
            f"{BASE_DATA}/sabnzbd/config:/config",
            f"{MEDIA_PATH}/downloads/usenet:/downloads",
            f"{MEDIA_PATH}/downloads/usenet/incomplete:/incomplete-downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    "nzbget": {
        "image": "linuxserver/nzbget:latest",
        "category": "download",
        "description": "Efficient Usenet downloader",
        "ports": ["6789:6789"],
        "volumes": [
            f"{BASE_DATA}/nzbget/config:/config",
            f"{MEDIA_PATH}/downloads/usenet:/downloads",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    "autobrr": {
        "image": "autobrr/autobrr:latest",
        "category": "download",
        "description": "IRC and RSS automation for grabbing releases",
        "ports": ["7474:7474"],
        "volumes": [
            f"{BASE_DATA}/autobrr/config:/config",
        ],
        "environment": {
            "PUID": "1000",
            "PGID": "1000",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
    },
    "unpackerr": {
        "image": "golift/unpackerr:latest",
        "category": "download",
        "description": "Extracts downloaded archives for *arr apps",
        "ports": [],
        "volumes": [
            f"{MEDIA_PATH}/downloads:/downloads",
        ],
        "environment": {
            "UN_SONARR_0_URL": "http://sonarr:8989",
            "UN_SONARR_0_API_KEY": "",
            "UN_RADARR_0_URL": "http://radarr:7878",
            "UN_RADARR_0_API_KEY": "",
            "UN_DELETE_ORIGINAL_FILE": "false",
            "UN_PARALLEL": "1",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": ["sonarr", "radarr"],
    },
    "gluetun": {
        "image": "qmcgaw/gluetun:latest",
        "category": "infrastructure",
        "description": "VPN client container — routes traffic through VPN",
        "ports": ["8888:8888"],
        "volumes": [
            f"{BASE_DATA}/gluetun:/gluetun",
        ],
        "environment": {
            "VPN_SERVICE_PROVIDER": "mullvad",
            "VPN_TYPE": "wireguard",
            "WIREGUARD_PRIVATE_KEY": "",
            "WIREGUARD_ADDRESSES": "",
            "TZ": "UTC",
        },
        "restart": "unless-stopped",
        "depends_on": [],
        "cap_add": ["NET_ADMIN"],
        "devices": ["/dev/net/tun:/dev/net/tun"],
    },
}


# ── Dependency resolution ──────────────────────────────────────────────────────

def resolve_deps(selected: list[str]) -> list[str]:
    """Topologically sort selected services including any required dependencies."""
    all_ids = set(selected)
    # Auto-add required dependencies
    for svc_id in selected:
        svc = SERVICE_CATALOG.get(svc_id, {})
        for dep in svc.get("depends_on", []):
            if dep in SERVICE_CATALOG:
                all_ids.add(dep)

    ordered: list[str] = []
    visited: set[str] = set()

    def visit(sid: str) -> None:
        if sid in visited:
            return
        visited.add(sid)
        for dep in SERVICE_CATALOG.get(sid, {}).get("depends_on", []):
            if dep in all_ids:
                visit(dep)
        ordered.append(sid)

    for sid in all_ids:
        visit(sid)

    return ordered


# ── YAML generation ───────────────────────────────────────────────────────────

def generate_compose(
    selected: list[str],
    network_name: str = NETWORK,
    base_data: str = BASE_DATA,
    media_path: str = MEDIA_PATH,
    timezone: str = "UTC",
    puid: int = 1000,
    pgid: int = 1000,
    external_plex_url: str = "",
) -> str:
    """Generate a complete docker-compose.yml as a string.

    If external_plex_url is set, Plex is not added as a service —
    Overseerr and other apps that need Plex will use that URL instead.
    """
    ordered = resolve_deps(selected)

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    services: CommentedMap = CommentedMap()

    # If external Plex is configured, skip generating the plex service
    skip_services = set()
    if external_plex_url:
        skip_services.add("plex")

    for svc_id in ordered:
        if svc_id not in SERVICE_CATALOG:
            continue
        if svc_id in skip_services:
            continue
        template = SERVICE_CATALOG[svc_id]

        svc: CommentedMap = CommentedMap()
        svc["image"] = template["image"]
        svc["container_name"] = svc_id
        svc["restart"] = template["restart"]

        if template.get("cap_add"):
            svc["cap_add"] = template["cap_add"]

        if template.get("devices"):
            svc["devices"] = template["devices"]

        if template["ports"]:
            ports = CommentedSeq()
            for p in template["ports"]:
                ports.append(DQ(p))
            svc["ports"] = ports

        if template["volumes"]:
            vols = CommentedSeq()
            for v in template["volumes"]:
                # Substitute base_data and media_path
                v = v.replace(BASE_DATA, base_data).replace(MEDIA_PATH, media_path)
                vols.append(v)
            svc["volumes"] = vols

        if template["environment"]:
            env: CommentedMap = CommentedMap()
            for k, v in template["environment"].items():
                val = str(v)
                if k == "TZ":
                    val = timezone
                elif k in ("PUID",):
                    val = str(puid)
                elif k in ("PGID",):
                    val = str(pgid)
                env[k] = val
            # Inject external Plex URL into Overseerr config
            if svc_id == "overseerr" and external_plex_url:
                env["PLEX_HOSTNAME"] = external_plex_url.rstrip("/").replace("http://", "").replace("https://", "").split(":")[0]
                env["PLEX_PORT"] = external_plex_url.rstrip("/").split(":")[-1] if ":" in external_plex_url.split("//")[-1] else "32400"
                env["PLEX_URL_OVERRIDE"] = external_plex_url.rstrip("/")
            svc["environment"] = env

        deps = [d for d in template.get("depends_on", []) if d in set(ordered) and d not in skip_services]
        if deps:
            dep_map: CommentedMap = CommentedMap()
            for d in deps:
                cond: CommentedMap = CommentedMap()
                cond["condition"] = "service_started"
                dep_map[d] = cond
            svc["depends_on"] = dep_map

        # Traefik labels for all services
        labels = CommentedSeq()
        labels.append(DQ("traefik.enable=false"))
        labels.append(DQ(f"traefik.http.routers.{svc_id}.entrypoints=websecure"))
        labels.append(DQ(f"traefik.http.routers.{svc_id}.tls.certresolver=letsencrypt"))
        svc["labels"] = labels

        svc.yaml_set_comment_before_after_key(
            "image", before=f"\n  # {template['description']}"
        )
        services[svc_id] = svc

    doc: CommentedMap = CommentedMap()
    doc["services"] = services

    net: CommentedMap = CommentedMap()
    net_inner: CommentedMap = CommentedMap()
    net_inner["driver"] = "bridge"
    net[network_name] = net_inner
    doc["networks"] = net

    # Add network to every service
    for svc_id in services:
        services[svc_id]["networks"] = [network_name]

    import io
    buf = io.StringIO()
    yaml.dump(doc, buf)
    return buf.getvalue()


# ── Save and deploy ───────────────────────────────────────────────────────────

def save_compose(content: str, path: str = OUTPUT_FILE) -> str:
    """Write compose content to disk, backing up any existing file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        shutil.copy2(path, path + ".bak")
    with open(path, "w") as f:
        f.write(content)
    return path


def deploy_compose(path: str = OUTPUT_FILE) -> dict[str, Any]:
    """Run docker compose up -d on the generated file."""
    cmd = ["docker", "compose", "-f", path, "up", "-d"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=os.path.dirname(path),
        )
        return {
            "success": result.returncode == 0,
            "command": " ".join(cmd),
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "command": " ".join(cmd),
                "stdout": "", "stderr": "Timed out after 300 seconds.", "returncode": -1}
    except FileNotFoundError:
        return {"success": False, "command": " ".join(cmd),
                "stdout": "", "stderr": "Docker CLI not found.", "returncode": -1}

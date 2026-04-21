"""Docker Compose generator.

Given a StackRequest (list of services + global options), produce a
deterministic, validated docker-compose.yml that:

  - declares Traefik with LEGO_DNS_TIMEOUT=300 and delayBeforeCheck=60
    so DNS-01 actually succeeds on Cloudflare
  - never creates duplicate environment keys
  - uses wildcard labels only when a service has a web_port
  - writes the file atomically via a .tmp + rename
  - keeps a .bak of the previous file so rollback is one shell command

The generator is the single source of truth for stack layout. The
stack builder UI never hand-crafts compose YAML — it submits a
StackRequest and this module produces the file.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from .catalog import CATALOG, ServiceDef, get
from .config import config
from .models import ServiceChoice, StackRequest
from .validators import validate_compose_file

logger = logging.getLogger(__name__)


# Name of the shared Docker network every stack service joins.
# Traefik must be on the same network to see the other containers.
STACK_NETWORK = "mediastack"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(request: StackRequest) -> str:
    """Produce the full docker-compose.yml text for the given request.

    Does not write to disk — the caller chooses when to persist.
    Raises ValueError on invalid input (unknown service keys, etc.).
    """
    # Validate service keys up front so errors are clear.
    for choice in request.services:
        if choice.enabled and get(choice.key) is None:
            raise ValueError(f"Unknown service: {choice.key}")

    services_section: dict[str, Any] = {}
    domain = (request.domain or "").strip() or None

    for choice in request.services:
        if not choice.enabled:
            continue
        svc_def = get(choice.key)
        if svc_def is None:
            continue
        # Special case: if user has external Plex, skip the Plex service
        # but still install Overseerr with PLEX_URL set externally.
        if svc_def.key == "plex" and request.external_plex_url:
            continue
        rendered = _render_service(svc_def, request, domain)
        services_section[svc_def.key] = rendered

    # Always add Traefik if any web-facing service was selected.
    if domain and _has_web_service(request) and "traefik" not in services_section:
        traefik_def = CATALOG["traefik"]
        services_section["traefik"] = _render_service(traefik_def, request, domain)

    compose: dict[str, Any] = {
        "services": services_section,
        "networks": {
            STACK_NETWORK: {
                "name": STACK_NETWORK,
                "driver": "bridge",
            }
        },
    }

    # Dump with a stable key order and no aliases/anchors so diffs are clean.
    return yaml.safe_dump(
        compose,
        sort_keys=False,
        default_flow_style=False,
        width=120,
        allow_unicode=True,
    )


def write(request: StackRequest, target: Path | None = None) -> Path:
    """Generate and persist the compose file.

    Writes atomically (tmp + rename) and keeps a `.bak` of the previous
    file. Validates the output before returning — raises ValueError if
    the generated YAML fails validation.
    """
    target = target or (config.stack_dir / "docker-compose.yml")
    target.parent.mkdir(parents=True, exist_ok=True)

    text = generate(request)

    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text)

    # Validate the tmp file before we swap it in. If it's broken, leave
    # the existing compose file alone and raise.
    issues = validate_compose_file(tmp)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        try:
            tmp.unlink()
        except OSError:
            pass
        msgs = "; ".join(i.message for i in errors)
        raise ValueError(f"Generated compose failed validation: {msgs}")

    # Backup the old file before overwriting
    if target.exists():
        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, bak)
    tmp.replace(target)

    logger.info("Wrote compose file: %s (%d bytes)", target, len(text))
    return target


# ---------------------------------------------------------------------------
# Internal rendering
# ---------------------------------------------------------------------------


def _has_web_service(request: StackRequest) -> bool:
    """True if any enabled service has a web UI (so we need Traefik)."""
    for choice in request.services:
        if not choice.enabled:
            continue
        svc = get(choice.key)
        if svc and svc.web_port and not svc.skip_traefik:
            return True
    return False


def _render_service(
    svc: ServiceDef,
    request: StackRequest,
    domain: str | None,
) -> dict[str, Any]:
    """Build the compose dict for one service.

    This function is the choke point where we enforce all our invariants:
    unique env keys, correct networks, proper Traefik labels, etc.
    """
    if svc.key == "traefik":
        return _render_traefik(request, domain)

    if svc.key == "cloudflared":
        return _render_cloudflared(request)

    if svc.key == "tailscale":
        return _render_tailscale(request)

    # Standard LinuxServer-style service
    svc_dict: dict[str, Any] = {
        "image": svc.image,
        "container_name": svc.key,
        "restart": "unless-stopped",
        "networks": [STACK_NETWORK],
    }

    # Environment — PUID/PGID/TZ are standard for linuxserver.io images.
    env: dict[str, str] = {
        "PUID": str(request.puid),
        "PGID": str(request.pgid),
        "TZ": request.timezone,
    }
    env.update(svc.env)
    # SABnzbd claim its own 8080 — remap at env level, and we'll remap
    # the host port too via extra_ports to avoid collision with qbit.
    if svc.key == "sabnzbd":
        env.setdefault("WEB_PORT", "8085")
    svc_dict["environment"] = env

    # Volumes: config path is local to the stack; media is the shared root.
    vols: list[str] = []
    for v in svc.config_volumes:
        vols.append(f"{request.config_root}/{svc.key}:{v}")
    for v in svc.media_volumes:
        vols.append(f"{request.media_root}:{v}")
    if vols:
        svc_dict["volumes"] = vols

    # Port mappings. For services with a web UI we still expose the
    # host port — some users want direct LAN access without going
    # through Traefik.
    ports: list[str] = []
    if svc.web_port:
        host_port = svc.web_port
        # Special case: SAB and qbit both default to 8080
        if svc.key == "sabnzbd":
            host_port = 8085
        ports.append(f"{host_port}:{svc.web_port}")
    ports.extend(svc.extra_ports)
    if ports:
        svc_dict["ports"] = ports

    if svc.depends_on:
        svc_dict["depends_on"] = list(svc.depends_on)

    if svc.command:
        svc_dict["command"] = svc.command

    # Traefik labels — only add if we have a domain and this service
    # has a web port. Services like cloudflared skip these entirely.
    # Also skip for services marked cf_tunnel_unsuitable when cloudflared
    # is in the stack — we don't want Plex routed through Cloudflare.
    has_cloudflared = any(
        s.key == "cloudflared" and s.enabled for s in request.services
    )
    skip_cf_unsuitable = has_cloudflared and svc.cf_tunnel_unsuitable

    if domain and svc.web_port and not svc.skip_traefik and not skip_cf_unsuitable:
        svc_dict["labels"] = _traefik_labels(svc, domain, request.cert_resolver)

    # Overseerr with external Plex: inject the URL as an env var
    # so the Overseerr setup wizard can find it.
    if svc.key == "overseerr" and request.external_plex_url:
        svc_dict["environment"]["PLEX_URL"] = request.external_plex_url

    return svc_dict


def _traefik_labels(svc: ServiceDef, domain: str, resolver: str) -> list[str]:
    """Produce the minimal, correct Traefik label set for a web service.

    The old generator only set `enable=true` and `Host(...)` which left
    Traefik unable to pick a cert resolver, so every router showed as
    pending. We now include `tls.certresolver` and `tls=true` so the
    resolver kicks in automatically.
    """
    host = f"{svc.key}.{domain}"
    router = svc.key
    # Wildcard cert covers all subdomains — bundle the tls section so
    # Traefik issues a single cert for *.<domain> rather than one per
    # subdomain. This is much faster and avoids Let's Encrypt rate limits.
    return [
        "traefik.enable=true",
        f"traefik.http.routers.{router}.rule=Host(`{host}`)",
        f"traefik.http.routers.{router}.entrypoints=websecure",
        f"traefik.http.routers.{router}.tls=true",
        f"traefik.http.routers.{router}.tls.certresolver={resolver}",
        f"traefik.http.routers.{router}.tls.domains[0].main={domain}",
        f"traefik.http.routers.{router}.tls.domains[0].sans=*.{domain}",
        f"traefik.http.services.{router}.loadbalancer.server.port={svc.web_port}",
    ]


def _render_traefik(request: StackRequest, domain: str | None) -> dict[str, Any]:
    """Compose entry for Traefik itself.

    Traefik reads its static config from traefik.yml (mounted from the
    host). The compose-level env vars are just the CF token and the
    LEGO timeout that fixed our cert issues.
    """
    env: dict[str, str] = {
        "LEGO_DNS_TIMEOUT": "300",  # default is too short for Cloudflare
    }
    if request.cloudflare_token:
        env["CF_DNS_API_TOKEN"] = request.cloudflare_token

    return {
        "image": "traefik:latest",
        "container_name": "traefik",
        "restart": "unless-stopped",
        "networks": [STACK_NETWORK],
        "ports": ["80:80", "443:443", "8081:8081"],
        "environment": env,
        "volumes": [
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            f"{request.config_root}/traefik:/etc/traefik",
            f"{request.config_root}/traefik/letsencrypt:/letsencrypt",
        ],
        # No Traefik labels on Traefik itself — dashboard uses the
        # `insecure: true` API on port 8081 which is LAN-only.
    }


def _render_cloudflared(request: StackRequest) -> dict[str, Any]:
    """Cloudflare Tunnel daemon. Requires TUNNEL_TOKEN to be set in .env."""
    return {
        "image": "cloudflare/cloudflared:latest",
        "container_name": "cloudflared",
        "restart": "unless-stopped",
        "networks": [STACK_NETWORK],
        # Command is required — the default entrypoint alone won't run.
        "command": "tunnel --no-autoupdate run",
        "environment": {
            "TUNNEL_TOKEN": "${CLOUDFLARED_TOKEN}",
        },
    }


def _render_tailscale(request: StackRequest) -> dict[str, Any]:
    """Tailscale VPN container.

    Tailscale needs NET_ADMIN capability and access to /dev/net/tun to
    create the tunnel interface. We persist state to the config volume
    so the node keeps its identity across container restarts — without
    this, every restart uses a new ephemeral auth key and the node
    disappears from the tailnet.

    TS_ROUTES: comma-separated CIDR(s) to advertise as subnet routes.
    Set to the Docker network subnet (e.g. 172.20.0.0/16) so that all
    stack containers are reachable from your tailnet without installing
    Tailscale on each one.

    Tailscale and Cloudflare Tunnel serve different purposes and can
    run simultaneously:
      - Cloudflare Tunnel: public internet access (Overseerr, Plex)
      - Tailscale: private access from enrolled devices (Sonarr, Radarr, RAD)
    """
    ts_config = f"{request.config_root}/tailscale"
    return {
        "image": "tailscale/tailscale:latest",
        "container_name": "tailscale",
        "restart": "unless-stopped",
        "networks": [STACK_NETWORK],
        "cap_add": ["NET_ADMIN", "NET_RAW"],
        "devices": ["/dev/net/tun:/dev/net/tun"],
        "volumes": [
            f"{ts_config}:/var/lib/tailscale",
        ],
        "environment": {
            "TS_AUTHKEY": request.tailscale_auth_key or "${TS_AUTHKEY}",
            "TS_ROUTES": request.tailscale_routes or "${TS_ROUTES:-}",
            "TS_HOSTNAME": request.tailscale_hostname or "mediastack",
            "TS_ACCEPT_DNS": "true",
            "TS_STATE_DIR": "/var/lib/tailscale",
            "TS_USERSPACE": "false",
            "TS_EXTRA_ARGS": "${TS_EXTRA_ARGS:-}",
        },
    }


# ---------------------------------------------------------------------------
# Traefik static config generator
# ---------------------------------------------------------------------------


TRAEFIK_YAML_TEMPLATE = """# Generated by MediaStack-RAD — do not edit by hand.
# The stack builder re-generates this file; manual edits are preserved
# in a .bak file. Regenerate by running the stack builder again.

api:
  dashboard: true
  # insecure: true exposes the dashboard on :8081 over plain HTTP.
  # Safe on a LAN; do NOT port-forward 8081.
  insecure: true

entryPoints:
  web:
    address: ":80"
    # Automatically redirect HTTP to HTTPS
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"
  traefik:
    address: ":8081"

providers:
  docker:
    exposedByDefault: false
    # Use the direct socket. The tecnativa/docker-socket-proxy has a
    # version negotiation bug that breaks with current Traefik.
    endpoint: "unix:///var/run/docker.sock"
    network: "{network}"

certificatesResolvers:
  letsencrypt:
    acme:
      email: {email}
      storage: /letsencrypt/acme.json
      dnsChallenge:
        provider: cloudflare
        # 60 second delay before checking propagation. Values below 30
        # frequently cause timeouts on Cloudflare.
        delayBeforeCheck: 60
        resolvers:
          - "1.1.1.1:53"
          - "8.8.8.8:53"

log:
  level: INFO

accessLog: {{}}
"""


def generate_traefik_yaml(email: str, network: str = STACK_NETWORK) -> str:
    """Produce a known-good traefik.yml with our defaults."""
    return TRAEFIK_YAML_TEMPLATE.format(email=email, network=network)

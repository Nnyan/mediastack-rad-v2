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
from .models import PortConflict, ServiceChoice, StackRequest, StackValidation, ValidationIssue
from .validators import validate_compose_file

logger = logging.getLogger(__name__)


# Name of the shared Docker network every stack service joins.
# Traefik must be on the same network to see the other containers.
STACK_NETWORK = "mediastack"


def _esc(value: str) -> str:
    """Escape $ in user-supplied values so Docker Compose doesn't interpolate them.

    Bcrypt hashes look like '$2b$10$...' — Docker Compose treats every '$X'
    as an environment variable reference and silently replaces it with an empty
    string. Doubling to '$$' makes Compose output a literal '$' at runtime.

    Values that ARE intentional placeholders (e.g. '${TINYAUTH_SECRET}') are
    left unchanged — they're meant to be resolved from .env.
    """
    if not value:
        return value
    # Placeholder pattern: starts with ${ and ends with } — leave as-is
    if value.startswith("${") and value.endswith("}"):
        return value
    return value.replace("$", "$$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pre-generation validation
# ---------------------------------------------------------------------------


def validate_request(request: StackRequest) -> StackValidation:
    """Check a StackRequest for missing required fields before generating.

    Returns a StackValidation with structured errors and warnings.
    Callers should abort generation if valid=False.
    """
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    enabled_keys = {s.key for s in request.services if s.enabled}

    # Domain required when any web-facing service is selected
    if not request.domain and any(
        get(k) and get(k).web_port and not get(k).skip_traefik
        for k in enabled_keys
    ):
        errors.append(ValidationIssue(
            severity="error",
            message="Domain is required — at least one selected service needs a domain for HTTPS routing.",
        ))

    # Cloudflare token required when cloudflared selected
    if "cloudflared" in enabled_keys and not request.cloudflare_token:
        errors.append(ValidationIssue(
            service="cloudflared", field="cloudflare_token",
            severity="error",
            message="CF_DNS_API_TOKEN is required for DNS-01 certificate issuance. "
                    "Generate at dash.cloudflare.com → My Profile → API Tokens "
                    "(Zone:DNS:Edit + Zone:Zone:Read).",
        ))

    # Plex claim — warning only (it's optional after first boot)
    if "plex" in enabled_keys and not request.plex_claim and not request.external_plex_url:
        warnings.append(ValidationIssue(
            service="plex", field="plex_claim",
            severity="warning",
            message="PLEX_CLAIM is not set. Plex will start but won't be linked to your account "
                    "on first boot. Get a 4-minute token at plex.tv/claim.",
        ))

    # Tailscale auth key required
    if "tailscale" in enabled_keys and not request.tailscale_auth_key:
        errors.append(ValidationIssue(
            service="tailscale", field="tailscale_auth_key",
            severity="error",
            message="TS_AUTHKEY is required. Generate a reusable, non-ephemeral key at "
                    "login.tailscale.com/admin/settings/keys.",
        ))

    # Tinyauth required fields
    if "tinyauth" in enabled_keys or request.tinyauth_enabled:
        for field, label, val in [
            ("tinyauth_users",   "TINYAUTH_AUTH_USERS", request.tinyauth_users),
            ("tinyauth_app_url", "TINYAUTH_APPURL",     request.tinyauth_app_url),
        ]:
            if not val or not val.strip():
                errors.append(ValidationIssue(
                    service="tinyauth", field=field,
                    severity="error",
                    message=f"Tinyauth {label} is required. Without it the auth gateway "
                            f"will not start.",
                ))

    return StackValidation(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def check_port_conflicts(
    request: StackRequest,
    running_ports: dict[int, str],
) -> list[PortConflict]:
    """Detect host-port clashes between selected services and running containers.

    running_ports: map of host_port → container_name for all currently running
    containers that are NOT part of the services being deployed (so redeploying
    the same stack doesn't generate false conflicts).

    Returns a list of PortConflict objects with suggested alternatives.
    """
    enabled_keys = {s.key for s in request.services if s.enabled}
    overrides = {s.key: s.port_override for s in request.services if s.port_override}

    # Ports already claimed within THIS request (accumulate as we go)
    claimed_by_request: set[int] = set()

    # Collect extra_ports from all enabled services to include in conflict check
    conflicts: list[PortConflict] = []

    for key in enabled_keys:
        svc = get(key)
        if not svc or not svc.web_port:
            continue
        host_port = overrides.get(key) or svc.web_port
        if host_port in running_ports or host_port in claimed_by_request:
            conflict_with = running_ports.get(host_port, "another selected service")
            suggested = _suggest_port(host_port, running_ports, claimed_by_request, enabled_keys)
            conflicts.append(PortConflict(
                service=key,
                port=host_port,
                conflict_with=conflict_with,
                suggested_port=suggested,
            ))
            claimed_by_request.add(suggested)
        else:
            claimed_by_request.add(host_port)

    return conflicts


def _suggest_port(
    base: int,
    running_ports: dict[int, str],
    claimed: set[int],
    enabled_keys: set[str],
) -> int:
    """Find the next available port starting from base+1."""
    # Collect all ports used by catalog services so we don't suggest
    # a port that would conflict with another known service
    catalog_ports: set[int] = {
        svc.web_port for svc in CATALOG.values()
        if svc.web_port and svc.key not in enabled_keys
    }
    forbidden = set(running_ports.keys()) | claimed | catalog_ports
    candidate = base + 1
    while candidate in forbidden or candidate > 65535:
        candidate += 1
    return candidate



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
        rendered = _render_service(svc_def, request, domain, choice)
        services_section[svc_def.key] = rendered

    # Always add Traefik if any web-facing service was selected.
    if domain and _has_web_service(request) and "traefik" not in services_section:
        traefik_def = CATALOG["traefik"]
        services_section["traefik"] = _render_service(traefik_def, request, domain, None)

    compose: dict[str, Any] = {
        "services": services_section,
        "networks": {
            STACK_NETWORK: {
                "name": STACK_NETWORK,
                "driver": "bridge",
            }
        },
    }

    # Merge any custom YAML fragment the user added via the custom app panel.
    # Custom services are merged in last so they can reference the stack network.
    if request.custom_yaml and request.custom_yaml.strip():
        try:
            custom_doc = yaml.safe_load(request.custom_yaml) or {}
            for svc_name, svc_cfg in (custom_doc.get("services") or {}).items():
                if isinstance(svc_cfg, dict):
                    # Add the stack network so Traefik can route to it
                    svc_cfg.setdefault("networks", [STACK_NETWORK])
                    svc_cfg.setdefault("restart", "unless-stopped")
                    compose["services"][svc_name] = svc_cfg
        except yaml.YAMLError as e:
            raise ValueError(f"custom_yaml parse error: {e}")

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
    choice: "ServiceChoice | None" = None,
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

    if svc.key == "tinyauth":
        return _render_tinyauth(request)

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
    # choice.port_override lets the user change the host-side port when there's
    # a conflict. The container-side port (svc.web_port) never changes —
    # Traefik routes to that and must stay stable.
    ports: list[str] = []
    if svc.web_port:
        host_port = (choice.port_override if choice and choice.port_override else svc.web_port)
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
        svc_dict["labels"] = _traefik_labels(svc, domain, request.cert_resolver, request)

    # Plex claim token — required on first boot to register with your account.
    # Expires 4 minutes after generation from plex.tv/claim, so it's passed
    # through here rather than hardcoded in the catalog.
    if svc.key == "plex" and request.plex_claim:
        svc_dict["environment"]["PLEX_CLAIM"] = request.plex_claim
    if svc.key == "plex" and request.plex_server_name:
        svc_dict["hostname"] = request.plex_server_name

    # Overseerr with external Plex: inject the URL as an env var
    # so the Overseerr setup wizard can find it.
    if svc.key == "overseerr" and request.external_plex_url:
        svc_dict["environment"]["PLEX_URL"] = request.external_plex_url

    # Merge any per-service extra_env the user specified in the builder.
    # Applied last so user values override catalog and generator defaults.
    if choice and choice.extra_env:
        svc_dict["environment"].update(choice.extra_env)

    return svc_dict


def _traefik_labels(
    svc: ServiceDef,
    domain: str,
    resolver: str,
    request: "StackRequest | None" = None,
) -> list[str]:
    """Produce the Traefik label set for a web service.

    When Tinyauth is enabled we use the two-router pattern (Option C):

      Router 1: <name>-lan  priority=10  ClientIP(<lan_subnet>)  NO middleware
        → LAN users (10.0.0.0/22) pass straight through, no auth prompt.

      Router 2: <name>       priority=5   all other IPs            tinyauth-auth@docker
        → Tailscale users (100.64.x.x) and internet get challenged.

    Traefik evaluates the higher-priority router first. A LAN request
    matches Router 1 and never sees Router 2. A Tailscale request misses
    Router 1's ClientIP check and falls to Router 2 where Tinyauth gates it.

    This is architecturally clean: auth is enforced at the router level,
    not in a middleware chain where ordering matters. A misconfigured
    middleware cannot bypass this — the LAN router simply has no middleware
    at all, and the auth router has no IP allowlist bypass.
    """
    host = f"{svc.key}.{domain}"
    router = svc.key
    use_tinyauth = (
        request is not None
        and request.tinyauth_enabled
        and _has_tinyauth(request)
    )

    # Base labels shared by both router patterns
    base = [
        "traefik.enable=true",
        # Service definition — same for both routers
        f"traefik.http.services.{router}.loadbalancer.server.port={svc.web_port}",
        # TLS/cert config on the primary router
        f"traefik.http.routers.{router}.tls=true",
        f"traefik.http.routers.{router}.tls.certresolver={resolver}",
        f"traefik.http.routers.{router}.tls.domains[0].main={domain}",
        f"traefik.http.routers.{router}.tls.domains[0].sans=*.{domain}",
    ]

    if not use_tinyauth:
        # Simple single-router setup — no auth middleware
        return base + [
            f"traefik.http.routers.{router}.rule=Host(`{host}`)",
            f"traefik.http.routers.{router}.entrypoints=websecure",
        ]

    # Two-router pattern for Option C
    lan = (request.lan_subnet or "10.0.0.0/22").strip()
    return base + [
        # --- Router 1: LAN bypass (high priority, no middleware) ---
        f"traefik.http.routers.{router}-lan.rule=Host(`{host}`) && ClientIP(`{lan}`)",
        f"traefik.http.routers.{router}-lan.entrypoints=websecure",
        f"traefik.http.routers.{router}-lan.priority=10",
        f"traefik.http.routers.{router}-lan.tls=true",
        f"traefik.http.routers.{router}-lan.tls.certresolver={resolver}",
        f"traefik.http.routers.{router}-lan.service={router}",
        # --- Router 2: Catch-all with Tinyauth (low priority) ---
        f"traefik.http.routers.{router}.rule=Host(`{host}`)",
        f"traefik.http.routers.{router}.entrypoints=websecure",
        f"traefik.http.routers.{router}.priority=5",
        f"traefik.http.routers.{router}.middlewares=tinyauth-auth@docker",
        f"traefik.http.routers.{router}.service={router}",
    ]


def _has_tinyauth(request: "StackRequest") -> bool:
    """True if tinyauth is in the selected services."""
    return any(
        s.key == "tinyauth" and s.enabled
        for s in request.services
    )


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
    # Use the token if the user supplied it in the builder; fall back to the
    # ${CLOUDFLARED_TOKEN} placeholder which Docker Compose reads from .env.
    tunnel_token = request.cloudflare_tunnel_token or "${CLOUDFLARED_TOKEN}"
    return {
        "image": "cloudflare/cloudflared:latest",
        "container_name": "cloudflared",
        "restart": "unless-stopped",
        "networks": [STACK_NETWORK],
        "command": "tunnel --no-autoupdate run",
        "environment": {
            "TUNNEL_TOKEN": tunnel_token,
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


def _render_tinyauth(request: StackRequest) -> dict[str, Any]:
    """Tinyauth ForwardAuth container — gates Tailscale/WAN, passes LAN through.

    Tinyauth sits behind Traefik as a ForwardAuth endpoint. When a request
    hits the catch-all router (priority=5), Traefik calls Tinyauth at
    /api/auth before forwarding. Tinyauth returns 200 (allow) or 401
    (redirect to login page).

    The LAN bypass is handled entirely at the Traefik router level (two-router
    pattern in _traefik_labels) — Tinyauth never even sees LAN requests.

    Environment variables:
      SECRET      — random string used to sign session cookies. Generate:
                    python3 -c "import secrets; print(secrets.token_hex(32))"
      APP_URL     — base URL for the Tinyauth login page (your domain).
                    Used to set the cookie domain and redirect after login.
                    e.g. https://auth.nyrdalyrt.com
      USERS       — comma-separated user:bcrypt_hash pairs.
                    Generate a hash: htpasswd -nBC 10 "" | tr -d ':\\n'
                    Or: docker run --rm ghcr.io/steveiliop56/tinyauth:latest
                         generate-hash --password yourpassword
      TOTP_ENABLED — "true" to require TOTP (Google Authenticator) in
                     addition to password. Off by default.

    The ForwardAuth middleware definition lives as labels on this container
    so Traefik picks it up from Docker's label API. The middleware name
    "tinyauth-auth" is referenced by all protected routers.
    """
    # Tinyauth v5 env vars — all prefixed with TINYAUTH_, SECRET removed.
    env: dict[str, str] = {
        "TINYAUTH_APPURL":      request.tinyauth_app_url or "${TINYAUTH_APPURL}",
        "TINYAUTH_AUTH_USERS":  _esc(request.tinyauth_users or "${TINYAUTH_AUTH_USERS}"),
    }

    labels = [
        "traefik.enable=true",
        # ForwardAuth middleware — Traefik calls this before any protected route.
        # trustForwardHeader lets Tinyauth see the original client IP via
        # X-Forwarded-For (set by Traefik) rather than the Docker gateway IP.
        "traefik.http.middlewares.tinyauth-auth.forwardauth.address=http://tinyauth:3000/api/auth/traefik",
        "traefik.http.middlewares.tinyauth-auth.forwardauth.trustForwardHeader=true",
        # Forward the authenticated username header to upstream services.
        "traefik.http.middlewares.tinyauth-auth.forwardauth.authResponseHeaders=X-Auth-User,X-Auth-User-Groups",
    ]

    return {
        "image": "ghcr.io/steveiliop56/tinyauth:latest",
        "container_name": "tinyauth",
        "restart": "unless-stopped",
        "networks": [STACK_NETWORK],
        "environment": env,
        "labels": labels,
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

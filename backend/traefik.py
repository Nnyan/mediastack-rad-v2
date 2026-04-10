"""
Traefik integration — domain config, per-container label generation,
route verification via the Traefik dashboard API.
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Any

import docker
import docker.errors

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "traefik_config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "domain": "",
    "cert_type": "http",           # "http" | "wildcard"
    "certresolver": "letsencrypt",
    "entrypoint_http": "web",
    "entrypoint_https": "websecure",
    "traefik_api_url": "http://traefik:8080",
    "network": "mediastack",
    "middleware": "",              # optional middleware name e.g. "authelia@docker"
}


# ── Config persistence ────────────────────────────────────────────────────────

def load_config() -> dict[str, Any]:
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump({**DEFAULT_CONFIG, **cfg}, f, indent=2)


# ── Container helpers ─────────────────────────────────────────────────────────

def _container_port(container) -> int | None:
    """Return the primary container-side port."""
    exposed = (container.attrs.get("Config") or {}).get("ExposedPorts") or {}
    for port_proto in sorted(exposed.keys()):
        try:
            return int(port_proto.split("/")[0])
        except ValueError:
            pass
    ports = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
    for cp in sorted(ports.keys()):
        try:
            return int(cp.split("/")[0])
        except ValueError:
            pass
    return None


def _router_name(container_name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", container_name.lstrip("/").lower())


def _is_traefik(container) -> bool:
    name = container.name.lower()
    image = (container.attrs.get("Config") or {}).get("Image", "").lower()
    return "traefik" in name or "traefik" in image


# ── Label generation ──────────────────────────────────────────────────────────

def generate_labels(container, config: dict[str, Any]) -> dict[str, str]:
    """
    Return the full set of Traefik labels needed for this container.
    cert_type="http"     → per-router certresolver (HTTP-01 challenge)
    cert_type="wildcard" → tls=true only; wildcard cert already obtained by Traefik
    """
    domain      = config.get("domain", "")
    cert_type   = config.get("cert_type", "http")
    certresolver= config.get("certresolver", "letsencrypt")
    entrypoint  = config.get("entrypoint_https", "websecure")
    middleware  = config.get("middleware", "")

    name = _router_name(container.name)
    port = _container_port(container)

    labels: dict[str, str] = {
        "traefik.enable": "true",
        f"traefik.http.routers.{name}.entrypoints": entrypoint,
    }

    if domain:
        labels[f"traefik.http.routers.{name}.rule"] = f"Host(`{name}.{domain}`)"

    if cert_type == "wildcard":
        labels[f"traefik.http.routers.{name}.tls"] = "true"
    else:
        labels[f"traefik.http.routers.{name}.tls.certresolver"] = certresolver

    if middleware:
        labels[f"traefik.http.routers.{name}.middlewares"] = middleware

    if port:
        labels[f"traefik.http.services.{name}.loadbalancer.server.port"] = str(port)

    return labels


def labels_to_yaml_block(labels: dict[str, str], indent: int = 6) -> str:
    pad = " " * indent
    lines = [f"{' ' * (indent - 2)}labels:"]
    for k, v in sorted(labels.items()):
        lines.append(f'{pad}- "{k}={v}"')
    return "\n".join(lines)


def generate_full_compose_snippet(containers: list, config: dict[str, Any]) -> str:
    """Generate a services YAML block with Traefik labels for every container."""
    lines = ["services:"]
    for c in containers:
        if _is_traefik(c):
            continue
        name = c.name.lstrip("/")
        labels = generate_labels(c, config)
        lines.append(f"  {name}:")
        lines.append("    labels:")
        for k, v in sorted(labels.items()):
            lines.append(f'      - "{k}={v}"')
        lines.append("")
    return "\n".join(lines)


# ── Traefik API ───────────────────────────────────────────────────────────────

def _api_get(url: str, timeout: int = 4) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _fetch_routes(api_url: str) -> list[dict]:
    try:
        return _api_get(f"{api_url.rstrip('/')}/api/http/routers") or []
    except Exception:
        return []


def _fetch_overview(api_url: str) -> dict:
    try:
        return _api_get(f"{api_url.rstrip('/')}/api/overview")
    except Exception:
        return {}


def _find_traefik_container(client: docker.DockerClient):
    for c in client.containers.list():
        if _is_traefik(c):
            return c
    return None


# ── Per-container status ──────────────────────────────────────────────────────

def _container_status(container, config: dict[str, Any], traefik_routes: list[dict]) -> dict[str, Any]:
    name     = _router_name(container.name)
    domain   = config.get("domain", "")
    cur_labels = (container.attrs.get("Config") or {}).get("Labels") or {}
    traefik_labels = {k: v for k, v in cur_labels.items() if "traefik" in k.lower()}

    has_enable = cur_labels.get("traefik.enable") == "true"
    has_rule   = any(f".{name}." in k and ".rule" in k for k in cur_labels)
    has_tls    = any(f".{name}." in k and ".tls" in k for k in cur_labels)
    has_port   = any(f".{name}." in k and "loadbalancer" in k for k in cur_labels)
    configured = has_enable and has_rule and has_tls

    # Cross-check against live Traefik routes
    route_live   = False
    route_status = "not registered"
    for route in traefik_routes:
        if name in (route.get("name") or "").lower():
            route_live   = True
            route_status = route.get("status", "enabled")
            break

    suggested = generate_labels(container, config)

    # Diff: which suggested labels are missing from current?
    missing = {k: v for k, v in suggested.items() if cur_labels.get(k) != v}

    return {
        "id":             container.short_id,
        "name":           container.name,
        "router_name":    name,
        "status":         container.status,
        "port":           _container_port(container),
        "configured":     configured,
        "has_enable":     has_enable,
        "has_rule":       has_rule,
        "has_tls":        has_tls,
        "has_port":       has_port,
        "route_live":     route_live,
        "route_status":   route_status,
        "expected_url":   f"https://{name}.{domain}" if domain else None,
        "current_traefik_labels": traefik_labels,
        "suggested_labels":       suggested,
        "missing_labels":         missing,
        "labels_yaml":    labels_to_yaml_block(suggested),
    }


# ── Full stack status ─────────────────────────────────────────────────────────

def get_status(client: docker.DockerClient, config: dict[str, Any]) -> dict[str, Any]:
    traefik_c   = _find_traefik_container(client)
    api_url     = config.get("traefik_api_url", "http://traefik:8080")
    t_running   = traefik_c is not None and traefik_c.status == "running"
    api_reach   = False
    t_version   = None
    routes      = []

    if t_running:
        overview = _fetch_overview(api_url)
        if overview:
            api_reach = True
            t_version = overview.get("version")
            routes    = _fetch_routes(api_url)

    all_containers = client.containers.list(all=True)
    statuses = [
        _container_status(c, config, routes)
        for c in all_containers
        if not _is_traefik(c)
    ]

    configured = sum(1 for s in statuses if s["configured"])
    verified   = sum(1 for s in statuses if s["route_live"])

    return {
        "traefik": {
            "running":       t_running,
            "name":          traefik_c.name if traefik_c else None,
            "api_url":       api_url,
            "api_reachable": api_reach,
            "version":       t_version,
            "total_routes":  len(routes),
        },
        "config":  config,
        "summary": {
            "total":         len(statuses),
            "configured":    configured,
            "verified":      verified,
            "unconfigured":  len(statuses) - configured,
        },
        "containers": statuses,
    }

"""
Stack health checker — validates that API keys and service URLs are
correctly shared between containers in the mediastack.
"""

from typing import Any
import docker
import docker.errors
import re


MEDIASTACK_GRAPH = {
    "sonarr": {
        "provides_key_in_env": None,
        "default_port": 8989,
        "required_by": ["unpackerr", "bazarr", "autobrr"],
        "requires": ["prowlarr"],
    },
    "radarr": {
        "provides_key_in_env": None,
        "default_port": 7878,
        "required_by": ["unpackerr", "bazarr", "autobrr"],
        "requires": ["prowlarr"],
    },
    "prowlarr": {
        "provides_key_in_env": None,
        "default_port": 9696,
        "required_by": ["sonarr", "radarr"],
        "requires": [],
    },
    "plex": {
        "provides_key_in_env": None,
        "default_port": 32400,
        "required_by": ["overseerr", "seerr", "tautulli"],
        "requires": [],
    },
    "jellyfin": {
        "provides_key_in_env": None,
        "default_port": 8096,
        "required_by": ["jellyseerr"],
        "requires": [],
    },
    "qbittorrent": {
        "provides_key_in_env": None,
        "default_port": 8080,
        "required_by": ["sonarr", "radarr", "autobrr"],
        "requires": [],
    },
    "sabnzbd": {
        "provides_key_in_env": None,
        "default_port": 8085,
        "required_by": ["sonarr", "radarr"],
        "requires": [],
    },
    "bazarr": {
        "provides_key_in_env": None,
        "default_port": 6767,
        "required_by": [],
        "requires": ["sonarr", "radarr"],
    },
    "unpackerr": {
        "provides_key_in_env": None,
        "default_port": None,
        "required_by": [],
        "requires": ["sonarr", "radarr"],
    },
    "traefik": {
        "provides_key_in_env": None,
        "default_port": 8080,
        "required_by": [],
        "requires": [],
    },
    "autobrr": {
        "provides_key_in_env": None,
        "default_port": 7474,
        "required_by": [],
        "requires": ["sonarr", "radarr", "qbittorrent"],
    },
}

KNOWN_API_KEY_PATTERNS = [
    r"API_KEY",
    r"APIKEY",
    r"_KEY$",
    r"^UN_\w+_API_KEY",
    r"SONARR_API",
    r"RADARR_API",
    r"PROWLARR_API",
]

KNOWN_URL_PATTERNS = [
    r"_URL$",
    r"_HOST$",
    r"_ENDPOINT$",
]

SERVICE_KEY_HINTS = {
    "sonarr":     "Settings > General > API Key in the Sonarr web UI",
    "radarr":     "Settings > General > API Key in the Radarr web UI",
    "prowlarr":   "Settings > General > API Key in the Prowlarr web UI",
    "bazarr":     "Settings > General > API Key in the Bazarr web UI",
    "lidarr":     "Settings > General > API Key in the Lidarr web UI",
    "readarr":    "Settings > General > API Key in the Readarr web UI",
    "qbittorrent":"Tools > Web UI > Authentication password (not an API key)",
    "plex":       "Plex claim token from plex.tv/claim (one-time use)",
    "jellyfin":   "Dashboard > API Keys > New API Key",
}

KNOWN_CONNECTIONS = [
    {
        "from": "unpackerr",
        "to": "sonarr",
        "url_envs": ["UN_SONARR_0_URL"],
        "key_envs": ["UN_SONARR_0_API_KEY"],
        "expected_url_contains": "sonarr",
    },
    {
        "from": "unpackerr",
        "to": "radarr",
        "url_envs": ["UN_RADARR_0_URL"],
        "key_envs": ["UN_RADARR_0_API_KEY"],
        "expected_url_contains": "radarr",
    },
    {
        "from": "unpackerr",
        "to": "lidarr",
        "url_envs": ["UN_LIDARR_0_URL"],
        "key_envs": ["UN_LIDARR_0_API_KEY"],
        "expected_url_contains": "lidarr",
    },
    {
        "from": "bazarr",
        "to": "sonarr",
        "url_envs": ["SONARR_HOST", "SONARR_URL"],
        "key_envs": ["SONARR_APIKEY", "SONARR_API_KEY"],
        "expected_url_contains": "sonarr",
    },
    {
        "from": "bazarr",
        "to": "radarr",
        "url_envs": ["RADARR_HOST", "RADARR_URL"],
        "key_envs": ["RADARR_APIKEY", "RADARR_API_KEY"],
        "expected_url_contains": "radarr",
    },
]


def _get_env(container) -> dict[str, str]:
    env_list = container.attrs.get("Config", {}).get("Env") or []
    result = {}
    for entry in env_list:
        if "=" in entry:
            k, _, v = entry.partition("=")
            result[k] = v
    return result


def _normalise_name(name: str) -> str:
    return name.lstrip("/").lower().split("_")[0].split("-")[0]


def _is_api_key_set(val: str) -> bool:
    if not val:
        return False
    stripped = val.strip()
    return bool(stripped) and stripped not in ("", "changeme", "your-api-key", "YOUR_API_KEY", "xxxxx")


def check_stack(client: docker.DockerClient) -> dict[str, Any]:
    try:
        containers = client.containers.list(all=True)
    except Exception as e:
        return {"error": str(e)}

    container_map: dict[str, Any] = {}
    for c in containers:
        norm = _normalise_name(c.name)
        container_map[norm] = {
            "id": c.short_id,
            "name": c.name,
            "status": c.status,
            "env": _get_env(c),
            "networks": list((c.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys()),
        }

    results: list[dict[str, Any]] = []

    # 1. Service-to-service network checks
    for svc_name, meta in MEDIASTACK_GRAPH.items():
        if svc_name not in container_map:
            continue
        svc = container_map[svc_name]
        svc_nets = set(svc["networks"])

        for req in meta.get("requires", []):
            if req not in container_map:
                results.append({
                    "type": "missing_dependency",
                    "severity": "warning",
                    "service": svc["name"],
                    "target": req,
                    "status": "missing",
                    "message": f"{svc['name']} requires {req} but it is not running.",
                    "fix": f"Add {req} to your docker-compose.yml and start it.",
                })
                continue

            dep = container_map[req]
            dep_nets = set(dep["networks"])
            shared_nets = svc_nets & dep_nets

            if not shared_nets:
                results.append({
                    "type": "network_isolation",
                    "severity": "critical",
                    "service": svc["name"],
                    "target": dep["name"],
                    "status": "fail",
                    "message": f"{svc['name']} and {dep['name']} share no Docker networks.",
                    "fix": "Add both services to the same network in docker-compose.yml.",
                })
            else:
                results.append({
                    "type": "network",
                    "severity": "ok",
                    "service": svc["name"],
                    "target": dep["name"],
                    "status": "ok",
                    "message": f"Shared network: {', '.join(shared_nets)}",
                    "fix": None,
                })

    # 2. Known connection / API key checks
    for conn in KNOWN_CONNECTIONS:
        from_name = conn["from"]
        to_name = conn["to"]

        if from_name not in container_map or to_name not in container_map:
            continue

        from_env = container_map[from_name]["env"]
        from_svc_name = container_map[from_name]["name"]
        to_svc_name = container_map[to_name]["name"]

        key_set = any(_is_api_key_set(from_env.get(k, "")) for k in conn["key_envs"])
        url_set = any(from_env.get(u, "") for u in conn["url_envs"])
        url_val = next((from_env.get(u) for u in conn["url_envs"] if from_env.get(u)), "")
        url_looks_right = conn["expected_url_contains"] in url_val.lower() if url_val else False

        if key_set and url_set and url_looks_right:
            results.append({
                "type": "api_key",
                "severity": "ok",
                "service": from_svc_name,
                "target": to_svc_name,
                "status": "ok",
                "message": f"API key and URL configured for {to_svc_name}",
                "fix": None,
            })
        elif key_set and url_set and not url_looks_right:
            results.append({
                "type": "api_key",
                "severity": "warning",
                "service": from_svc_name,
                "target": to_svc_name,
                "status": "warn",
                "message": f"URL for {to_svc_name} may be wrong (got: {url_val})",
                "fix": f"URL should contain the container name '{to_name}', e.g. http://{to_name}:{MEDIASTACK_GRAPH.get(to_name, {}).get('default_port', 80)}",
            })
        elif not key_set:
            hint = SERVICE_KEY_HINTS.get(to_name, f"Check {to_name}'s Settings > General for its API key")
            results.append({
                "type": "api_key",
                "severity": "critical",
                "service": from_svc_name,
                "target": to_svc_name,
                "status": "fail",
                "message": f"API key for {to_svc_name} not set in {from_svc_name}",
                "fix": f"Find the key: {hint}. Then set env var {conn['key_envs'][0]}=<key>",
            })
        elif not url_set:
            results.append({
                "type": "api_key",
                "severity": "warning",
                "service": from_svc_name,
                "target": to_svc_name,
                "status": "warn",
                "message": f"URL for {to_svc_name} not configured in {from_svc_name}",
                "fix": f"Set env var {conn['url_envs'][0]}=http://{to_name}:{MEDIASTACK_GRAPH.get(to_name, {}).get('default_port', 80)}",
            })

    # 3. Scan for env vars that look like unset API keys
    for norm_name, svc in container_map.items():
        for key, val in svc["env"].items():
            is_key_var = any(re.search(p, key, re.IGNORECASE) for p in KNOWN_API_KEY_PATTERNS)
            if is_key_var and not _is_api_key_set(val):
                results.append({
                    "type": "empty_key",
                    "severity": "warning",
                    "service": svc["name"],
                    "target": None,
                    "status": "warn",
                    "message": f"Env var {key} appears to be an API key but is empty",
                    "fix": f"Set {key} to the correct value and restart {svc['name']}",
                })

    # Summarise
    critical = sum(1 for r in results if r["severity"] == "critical")
    warnings  = sum(1 for r in results if r["severity"] == "warning")
    ok        = sum(1 for r in results if r["severity"] == "ok")

    return {
        "summary": {"critical": critical, "warnings": warnings, "ok": ok, "total": len(results)},
        "healthy": critical == 0,
        "results": results,
        "key_hints": SERVICE_KEY_HINTS,
    }

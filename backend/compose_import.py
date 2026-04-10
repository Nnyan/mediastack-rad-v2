"""
Compose import — parses docker-compose YAML (pasted text or GitHub URL)
and returns structured service definitions for display in the UI.
"""

import re
import urllib.request
import urllib.error
from typing import Any

import yaml


def _parse_ports(ports: list | None) -> list[str]:
    if not ports:
        return []
    result = []
    for p in ports:
        result.append(str(p))
    return result


def _parse_env(env) -> dict[str, str]:
    if not env:
        return {}
    if isinstance(env, list):
        out = {}
        for e in env:
            if "=" in str(e):
                k, _, v = str(e).partition("=")
                out[k] = v
            else:
                out[str(e)] = ""
        return out
    if isinstance(env, dict):
        return {k: str(v) if v is not None else "" for k, v in env.items()}
    return {}


def _parse_volumes(vols: list | None) -> list[str]:
    if not vols:
        return []
    result = []
    for v in vols:
        if isinstance(v, str):
            result.append(v)
        elif isinstance(v, dict):
            src = v.get("source", "")
            tgt = v.get("target", "")
            if src and tgt:
                result.append(f"{src}:{tgt}")
    return result


def _guess_category(name: str, image: str) -> str:
    text = (name + " " + image).lower()
    if re.search(r"plex|emby|jellyfin|kodi", text):
        return "media"
    if re.search(r"torrent|nzb|sab|usenet|download|deluge|transmission|qbit|aria", text):
        return "download"
    if re.search(r"traefik|nginx|caddy|cloudflare|letsencrypt|wireguard|vpn|dns|pihole|authelia", text):
        return "infrastructure"
    return "management"


def _parse_compose_dict(data: dict) -> list[dict[str, Any]]:
    services_raw = data.get("services") or {}
    if not services_raw:
        raise ValueError("No 'services' key found in the compose file.")

    services = []
    for name, svc in services_raw.items():
        if not isinstance(svc, dict):
            continue
        image_raw = svc.get("image", name)
        image_parts = str(image_raw).rsplit(":", 1)
        image = image_parts[0]
        tag = image_parts[1] if len(image_parts) == 2 else "latest"

        depends_raw = svc.get("depends_on", [])
        if isinstance(depends_raw, dict):
            depends = list(depends_raw.keys())
        elif isinstance(depends_raw, list):
            depends = [str(d) for d in depends_raw]
        else:
            depends = []

        services.append({
            "name": svc.get("container_name") or name,
            "image": image,
            "tag": tag,
            "ports": _parse_ports(svc.get("ports")),
            "environment": _parse_env(svc.get("environment")),
            "volumes": _parse_volumes(svc.get("volumes")),
            "depends_on": depends,
            "restart": svc.get("restart", "unless-stopped"),
            "networks": list(svc.get("networks", {}).keys()) if isinstance(svc.get("networks"), dict) else svc.get("networks", []),
            "category": _guess_category(name, image),
        })

    return services


def parse_yaml_text(text: str) -> list[dict[str, Any]]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")
    if not isinstance(data, dict):
        raise ValueError("Compose file must be a YAML mapping.")
    return _parse_compose_dict(data)


def fetch_from_github(url: str) -> tuple[list[dict[str, Any]], str]:
    """
    Accepts various GitHub URL formats:
      - https://github.com/user/repo
      - https://github.com/user/repo/blob/main/docker-compose.yml
      - https://raw.githubusercontent.com/user/repo/main/docker-compose.yml

    Returns (services, raw_yaml_text).
    """
    raw_url = _resolve_raw_url(url)
    try:
        req = urllib.request.Request(
            raw_url,
            headers={"User-Agent": "mediastack-rad/2.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ValueError(f"GitHub returned HTTP {e.code} for {raw_url}")
    except urllib.error.URLError as e:
        raise ValueError(f"Cannot reach GitHub: {e.reason}")

    return parse_yaml_text(text), text


def _resolve_raw_url(url: str) -> str:
    url = url.strip().rstrip("/")

    # Already a raw URL
    if "raw.githubusercontent.com" in url:
        return url

    # blob URL: https://github.com/user/repo/blob/branch/path/file.yml
    blob_match = re.match(
        r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url
    )
    if blob_match:
        user, repo, branch, path = blob_match.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"

    # Bare repo URL: https://github.com/user/repo
    repo_match = re.match(r"https://github\.com/([^/]+)/([^/]+)$", url)
    if repo_match:
        user, repo = repo_match.groups()
        for branch in ("main", "master"):
            for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                raw = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{filename}"
                try:
                    req = urllib.request.Request(raw, headers={"User-Agent": "mediastack-rad/2.0"}, method="HEAD")
                    urllib.request.urlopen(req, timeout=5)
                    return raw
                except Exception:
                    continue
        raise ValueError(
            f"Could not find a docker-compose file in {url}. "
            "Try providing the direct link to the compose file."
        )

    raise ValueError(
        f"Unrecognised GitHub URL format: {url}. "
        "Use a repo URL (github.com/user/repo) or blob URL pointing to a compose file."
    )

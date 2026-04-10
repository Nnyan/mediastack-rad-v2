"""
Compose file auto-apply — patches Traefik labels into the user's
docker-compose.yml (preserving comments and formatting via ruamel.yaml)
and runs `docker compose up -d --no-deps <service>` to apply the changes.
"""

import os
import shutil
import subprocess
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

COMPOSE_FILE_ENV = "COMPOSE_FILE_PATH"
COMPOSE_SEARCH_PATHS = [
    "/compose/docker-compose.yml",
    "/compose/docker-compose.yaml",
    "/compose/compose.yml",
    "/compose/compose.yaml",
]


# ── System checks ─────────────────────────────────────────────────────────────

def find_compose_file() -> str | None:
    explicit = os.environ.get(COMPOSE_FILE_ENV, "").strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    for p in COMPOSE_SEARCH_PATHS:
        if os.path.isfile(p):
            return p
    return None


def system_status() -> dict[str, Any]:
    compose_path = find_compose_file()
    docker_bin = shutil.which("docker")
    socket_path = "/var/run/docker.sock"
    socket_exists = os.path.exists(socket_path)
    socket_writable = os.access(socket_path, os.W_OK) if socket_exists else False

    issues = []
    if not compose_path:
        issues.append(
            "Compose file not found. Mount your compose directory: "
            "add '- /path/to/your/stack:/compose' to mediastack-rad's volumes "
            "in your host's docker-compose.yml, then set COMPOSE_FILE_PATH=/compose/docker-compose.yml"
        )
    if not docker_bin:
        issues.append(
            "Docker CLI not found inside the container. "
            "Rebuild the image — the Dockerfile now includes the docker CLI."
        )
    if not socket_writable:
        issues.append(
            "Docker socket is read-only or missing. "
            "Remove ':ro' from the socket volume in docker-compose.yml: "
            "change '/var/run/docker.sock:/var/run/docker.sock:ro' "
            "to '/var/run/docker.sock:/var/run/docker.sock'"
        )

    return {
        "compose_path": compose_path,
        "compose_found": compose_path is not None,
        "docker_bin": docker_bin,
        "docker_available": docker_bin is not None,
        "socket_writable": socket_writable,
        "ready": len(issues) == 0,
        "issues": issues,
    }


# ── Compose service name resolution ───────────────────────────────────────────

def resolve_service_name(container, compose_path: str) -> str:
    """
    Resolve the compose service name for a container.
    Prefers the com.docker.compose.service label (set by docker compose),
    falls back to matching container_name or the container name itself.
    """
    labels = (container.attrs.get("Config") or {}).get("Labels") or {}

    # Best source: Docker Compose sets this label automatically
    compose_service = labels.get("com.docker.compose.service")
    if compose_service:
        return compose_service

    # Fall back: search the compose file for a matching container_name
    container_name = container.name.lstrip("/")
    try:
        yaml = YAML()
        yaml.preserve_quotes = True
        with open(compose_path) as f:
            data = yaml.load(f)
        services = data.get("services") or {}
        for key, svc in services.items():
            svc_cn = (svc or {}).get("container_name", "")
            if svc_cn == container_name or key == container_name:
                return key
    except Exception:
        pass

    return container_name


# ── YAML patching ─────────────────────────────────────────────────────────────

def patch_compose_labels(
    compose_path: str,
    service_name: str,
    labels: dict[str, str],
) -> tuple[str, list[str]]:
    """
    Inject/update Traefik labels for service_name in compose_path.
    Preserves all comments and formatting using ruamel.yaml.
    Always creates a .bak backup before writing.

    Returns (backup_path, list_of_changed_keys).
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # prevent unwanted line-wrapping

    with open(compose_path) as f:
        data = yaml.load(f)

    services = data.get("services") or {}
    if service_name not in services:
        available = list(services.keys())
        raise ValueError(
            f"Service '{service_name}' not found in compose file. "
            f"Available services: {available}"
        )

    svc = services[service_name]
    if svc is None:
        services[service_name] = {}
        svc = services[service_name]

    # Parse existing labels into a dict (handle both list and map formats)
    existing: dict[str, str] = {}
    raw_labels = svc.get("labels") or []
    if isinstance(raw_labels, list):
        for entry in raw_labels:
            entry_str = str(entry)
            if "=" in entry_str:
                k, _, v = entry_str.partition("=")
                existing[k.strip()] = v.strip()
    elif isinstance(raw_labels, dict):
        existing = {str(k): str(v) for k, v in raw_labels.items()}

    changed = [k for k, v in labels.items() if existing.get(k) != v]
    existing.update(labels)

    # Write back as list format (standard in most compose files)
    label_list = CommentedSeq([f"{k}={v}" for k, v in sorted(existing.items())])
    svc["labels"] = label_list

    # Backup original before writing
    backup_path = compose_path + ".bak"
    shutil.copy2(compose_path, backup_path)

    with open(compose_path, "w") as f:
        yaml.dump(data, f)

    return backup_path, changed


def preview_patch(
    compose_path: str,
    service_name: str,
    labels: dict[str, str],
) -> dict[str, Any]:
    """
    Return what would change without writing anything.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(compose_path) as f:
        data = yaml.load(f)

    services = data.get("services") or {}
    if service_name not in services:
        return {"error": f"Service '{service_name}' not found"}

    svc = services[service_name] or {}
    existing: dict[str, str] = {}
    raw = svc.get("labels") or []
    if isinstance(raw, list):
        for entry in raw:
            if "=" in str(entry):
                k, _, v = str(entry).partition("=")
                existing[k.strip()] = v.strip()
    elif isinstance(raw, dict):
        existing = {str(k): str(v) for k, v in raw.items()}

    added   = {k: v for k, v in labels.items() if k not in existing}
    changed = {k: v for k, v in labels.items() if k in existing and existing[k] != v}
    unchanged = {k: v for k, v in labels.items() if existing.get(k) == v}

    return {
        "service": service_name,
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "will_modify": len(added) + len(changed) > 0,
    }


# ── Docker compose execution ──────────────────────────────────────────────────

def run_compose_up(
    compose_path: str,
    service_name: str | None = None,
) -> dict[str, Any]:
    """
    Run `docker compose -f <path> up -d [--no-deps <service>]`.
    Returns stdout, stderr, exit code.
    """
    cmd = ["docker", "compose", "-f", compose_path, "up", "-d"]
    if service_name:
        cmd += ["--no-deps", service_name]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=os.path.dirname(compose_path),
        )
        return {
            "success":    result.returncode == 0,
            "stdout":     result.stdout.strip(),
            "stderr":     result.stderr.strip(),
            "returncode": result.returncode,
            "command":    " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False, "stdout": "",
            "stderr": "Command timed out after 180 seconds.",
            "returncode": -1, "command": " ".join(cmd),
        }
    except FileNotFoundError:
        return {
            "success": False, "stdout": "",
            "stderr": (
                "Docker CLI not found. Rebuild the container: "
                "docker compose up -d --build mediastack-rad"
            ),
            "returncode": -1, "command": " ".join(cmd),
        }


# ── High-level apply operation ────────────────────────────────────────────────

def apply_labels(
    container,
    compose_path: str,
    labels: dict[str, str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Patch compose file + run docker compose up for a single container.
    If dry_run=True, only returns the preview (no writes, no subprocess).
    """
    service_name = resolve_service_name(container, compose_path)

    if dry_run:
        return {"dry_run": True, **preview_patch(compose_path, service_name, labels)}

    try:
        backup_path, changed_keys = patch_compose_labels(compose_path, service_name, labels)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    run_result = run_compose_up(compose_path, service_name)

    return {
        "success":      run_result["success"],
        "service":      service_name,
        "compose_path": compose_path,
        "backup_path":  backup_path,
        "changed_keys": changed_keys,
        "command":      run_result["command"],
        "stdout":       run_result["stdout"],
        "stderr":       run_result["stderr"],
        "returncode":   run_result["returncode"],
    }


def apply_all_labels(
    containers: list,
    compose_path: str,
    labels_fn,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Patch labels for all containers and run `docker compose up -d` (all at once).
    labels_fn(container) → dict[str, str]
    """
    results = []
    errors  = []

    for container in containers:
        service_name = resolve_service_name(container, compose_path)
        labels = labels_fn(container)

        if dry_run:
            results.append({"dry_run": True, **preview_patch(compose_path, service_name, labels)})
            continue

        try:
            backup_path, changed_keys = patch_compose_labels(compose_path, service_name, labels)
            results.append({
                "service":      service_name,
                "changed_keys": changed_keys,
                "backup_path":  backup_path,
            })
        except ValueError as e:
            errors.append({"service": service_name, "error": str(e)})

    if dry_run:
        return {"dry_run": True, "services": results}

    # Single compose up for all services
    run_result = run_compose_up(compose_path, service_name=None)

    return {
        "success":  run_result["success"],
        "services": results,
        "errors":   errors,
        "command":  run_result["command"],
        "stdout":   run_result["stdout"],
        "stderr":   run_result["stderr"],
    }

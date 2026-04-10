"""
Troubleshoot engine — analyses container logs and inspect data,
returns structured findings with remediation steps.
"""

import re
from typing import Any

import docker
import docker.errors


RULES = [
    {
        "pattern": r"permission denied|operation not permitted",
        "title": "File permission error",
        "severity": "critical",
        "cause": "The container cannot read or write a mounted volume path.",
        "steps": [
            "Check host path ownership: ls -la <host-path>",
            "Set PUID/PGID env vars to match your host user (run: id $USER)",
            "Fix ownership: sudo chown -R 1000:1000 <host-path>",
            "Ensure the host path exists before starting the container",
        ],
    },
    {
        "pattern": r"address already in use|bind.*failed|port.*already allocated",
        "title": "Port conflict",
        "severity": "critical",
        "cause": "Another process or container is already using the mapped port.",
        "steps": [
            "Find what's using the port: sudo ss -tlnp | grep <port>",
            "Change the host port in docker-compose.yml (e.g. '8990:8989')",
            "Stop the conflicting container or service first",
        ],
    },
    {
        "pattern": r"no such file or directory|cannot find|not found",
        "title": "Missing file or path",
        "severity": "critical",
        "cause": "A required file, binary, or volume path does not exist.",
        "steps": [
            "Verify all host volume paths exist: ls -la <path>",
            "Create missing directories: mkdir -p <path>",
            "Check the image tag is correct — the file may not exist in that version",
        ],
    },
    {
        "pattern": r"connection refused|connection timed out|no route to host|cannot connect",
        "title": "Network connectivity failure",
        "severity": "high",
        "cause": "The container cannot reach a dependency (another service or external host).",
        "steps": [
            "Confirm the dependency container is running: docker ps",
            "Ensure both containers share the same Docker network",
            "Check service URLs use container names (not localhost) e.g. http://sonarr:8989",
            "Verify firewall rules are not blocking inter-container traffic",
        ],
    },
    {
        "pattern": r"invalid api key|unauthorized|403 forbidden|401",
        "title": "Invalid or missing API key",
        "severity": "high",
        "cause": "The app was given a wrong or empty API key for a connected service.",
        "steps": [
            "Open the dependency app's web UI and copy its API key from Settings > General",
            "Update the API key env var or config in this container",
            "Restart this container after updating: docker restart <name>",
        ],
    },
    {
        "pattern": r"database.*locked|sqlite.*locked|database is locked",
        "title": "Database lock error",
        "severity": "high",
        "cause": "Two processes are trying to access the SQLite database simultaneously.",
        "steps": [
            "Stop all instances of this container",
            "Do not run multiple replicas of *arr apps on the same config volume",
            "Check for orphaned lock files: find <config-path> -name '*.lock' -delete",
            "Restart the container: docker compose up -d <service>",
        ],
    },
    {
        "pattern": r"out of memory|oomkilled|killed.*memory",
        "title": "Out of memory (OOM kill)",
        "severity": "critical",
        "cause": "The container exceeded its memory limit and was killed by the kernel.",
        "steps": [
            "Check current memory limits in docker-compose.yml (mem_limit)",
            "Increase the limit or remove it to allow the container to use more RAM",
            "Check host available memory: free -h",
            "Reduce concurrent tasks in the app settings (e.g. lower parallel downloads)",
        ],
    },
    {
        "pattern": r"disk.*full|no space left|enospc",
        "title": "Disk full",
        "severity": "critical",
        "cause": "The host filesystem has no space left.",
        "steps": [
            "Check disk usage: df -h",
            "Remove unused Docker images: docker image prune -a",
            "Clear old container logs: docker system prune",
            "Free space on the volume where config/media is stored",
        ],
    },
    {
        "pattern": r"image.*not found|manifest.*not found|pull.*failed|repository.*does not exist",
        "title": "Image pull failure",
        "severity": "critical",
        "cause": "Docker cannot pull the container image — tag may be wrong or registry unreachable.",
        "steps": [
            "Verify the image name and tag in docker-compose.yml",
            "Test manually: docker pull <image>:<tag>",
            "Check internet connectivity from the host",
            "If using a private registry, ensure credentials are configured",
        ],
    },
    {
        "pattern": r"tls.*handshake|ssl.*error|certificate.*expired|certificate.*invalid",
        "title": "TLS / SSL certificate error",
        "severity": "high",
        "cause": "A TLS certificate is invalid, expired, or the host clock is wrong.",
        "steps": [
            "Check host system time: date — it must be accurate for TLS to work",
            "Sync the clock: sudo timedatectl set-ntp true",
            "If using Let's Encrypt: check Traefik logs for renewal errors",
            "Ensure port 80 is reachable for ACME HTTP challenge",
        ],
    },
    {
        "pattern": r"exec.*format error|cannot execute binary",
        "title": "Architecture mismatch",
        "severity": "critical",
        "cause": "The container image was built for a different CPU architecture.",
        "steps": [
            "Check your host architecture: uname -m",
            "Use an architecture-specific image tag (e.g. linux/arm64)",
            "Check the image supports your architecture on Docker Hub",
        ],
    },
]


def _get_env_dict(container) -> dict[str, str]:
    env_list = container.attrs.get("Config", {}).get("Env") or []
    result = {}
    for entry in env_list:
        if "=" in entry:
            k, _, v = entry.partition("=")
            result[k] = v
    return result


def _check_volumes(container) -> list[dict[str, Any]]:
    findings = []
    mounts = container.attrs.get("Mounts") or []
    for m in mounts:
        if m.get("Type") == "bind":
            host_path = m.get("Source", "")
            import os
            if not os.path.exists(host_path):
                findings.append({
                    "title": f"Volume path missing: {host_path}",
                    "severity": "critical",
                    "cause": f"Host path '{host_path}' does not exist on the filesystem.",
                    "steps": [
                        f"Create the directory: mkdir -p {host_path}",
                        "Set correct ownership: sudo chown -R 1000:1000 " + host_path,
                        "Restart the container after creating the path",
                    ],
                })
    return findings


def _check_oom(container) -> list[dict[str, Any]]:
    findings = []
    state = container.attrs.get("State", {})
    if state.get("OOMKilled"):
        findings.append({
            "title": "Container was OOM killed",
            "severity": "critical",
            "cause": "The container was killed by the kernel due to out-of-memory conditions.",
            "steps": [
                "Increase or remove the memory limit in docker-compose.yml",
                "Check host available memory: free -h",
                "Reduce workload: lower parallel tasks in app settings",
            ],
        })
    return findings


def _check_exit_code(container) -> list[dict[str, Any]]:
    findings = []
    state = container.attrs.get("State", {})
    exit_code = state.get("ExitCode", 0)
    if exit_code not in (0, None) and container.status != "running":
        msg = {
            1:   "General error — check logs for the specific cause",
            126: "Permission denied — cannot execute command inside container",
            127: "Command not found — the entrypoint or CMD binary is missing",
            137: "Killed (SIGKILL) — likely OOM or manual kill",
            139: "Segfault — possible corrupt image or incompatible binary",
            143: "Terminated (SIGTERM) — container was stopped gracefully",
        }.get(exit_code, f"Non-zero exit code {exit_code}")
        findings.append({
            "title": f"Exited with code {exit_code}",
            "severity": "high" if exit_code not in (143,) else "info",
            "cause": msg,
            "steps": [
                "Review the full container logs: docker logs <name> --tail 100",
                "Check the error message immediately before exit in the logs",
            ],
        })
    return findings


def _match_log_rules(logs: str) -> list[dict[str, Any]]:
    findings = []
    seen_titles = set()
    for rule in RULES:
        if re.search(rule["pattern"], logs, re.IGNORECASE):
            if rule["title"] not in seen_titles:
                findings.append({k: v for k, v in rule.items() if k != "pattern"})
                seen_titles.add(rule["title"])
    return findings


def diagnose(client: docker.DockerClient, container_id: str) -> dict[str, Any]:
    try:
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        return {"error": f"Container '{container_id}' not found"}

    findings: list[dict[str, Any]] = []

    findings.extend(_check_oom(container))
    findings.extend(_check_exit_code(container))
    findings.extend(_check_volumes(container))

    try:
        raw_logs = container.logs(tail=200).decode("utf-8", errors="replace")
        findings.extend(_match_log_rules(raw_logs))
    except Exception:
        raw_logs = ""

    severity_order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    findings.sort(key=lambda f: severity_order.get(f.get("severity", "info"), 3))

    return {
        "container": container.name,
        "status": container.status,
        "findings": findings,
        "healthy": len(findings) == 0,
        "summary": (
            f"{len(findings)} issue(s) found" if findings
            else "No obvious issues detected — check logs for more detail"
        ),
    }

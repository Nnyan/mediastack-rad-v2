"""
Port conflict checker — scans running containers AND the service catalog
to detect host port collisions before deploying a new stack.
"""

import re
import socket
from typing import Any


def _parse_host_port(port_str: str) -> int | None:
    """Extract the host-side port from a mapping like '8080:80' or '6881:6881/udp'."""
    s = str(port_str).split("/")[0]  # strip /udp, /tcp
    parts = s.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[-2])
        except ValueError:
            pass
    if len(parts) == 1:
        try:
            return int(parts[0])
        except ValueError:
            pass
    return None


def _host_ports_from_mapping(ports: list[str]) -> list[int]:
    result = []
    for p in ports:
        hp = _parse_host_port(p)
        if hp:
            result.append(hp)
    return result


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a TCP port is already bound on the host."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
    except OSError:
        return True


def get_running_port_map(docker_client) -> dict[int, str]:
    """
    Return {host_port: container_name} for all currently running containers.
    """
    port_map: dict[int, str] = {}
    try:
        containers = docker_client.containers.list()
    except Exception:
        return port_map

    for c in containers:
        network_settings = c.attrs.get("NetworkSettings") or {}
        ports = network_settings.get("Ports") or {}
        for _container_port, bindings in ports.items():
            if not bindings:
                continue
            for b in bindings:
                try:
                    hp = int(b.get("HostPort", 0))
                    if hp:
                        port_map[hp] = c.name
                except (ValueError, TypeError):
                    pass
    return port_map


def check_catalog_conflicts(catalog: dict[str, dict]) -> list[dict[str, Any]]:
    """
    Check all services in the catalog against each other for host port conflicts.
    Returns a list of conflict dicts.
    """
    port_to_services: dict[int, list[str]] = {}

    for svc_id, svc in catalog.items():
        for port_str in svc.get("ports", []):
            hp = _parse_host_port(port_str)
            if hp:
                port_to_services.setdefault(hp, []).append(svc_id)

    conflicts = []
    for port, services in port_to_services.items():
        if len(services) > 1:
            conflicts.append({
                "port": port,
                "services": services,
                "type": "catalog_conflict",
                "message": f"Port {port} is used by: {', '.join(services)}",
            })
    return conflicts


def check_selection(
    selected_services: list[str],
    catalog: dict[str, dict],
    docker_client=None,
    extra_ports: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """
    Full port conflict check for a proposed selection of services.

    Checks:
    1. Conflicts within the selected services themselves
    2. Conflicts with currently running Docker containers
    3. Conflicts with ports already bound on the host (socket check)

    extra_ports: {service_id: ["host:container", ...]} for custom-added services
    not in the catalog.
    """
    # Build port map for the selection
    selection_ports: dict[int, list[str]] = {}  # host_port -> [service_ids]

    for svc_id in selected_services:
        ports = []
        if svc_id in catalog:
            ports = catalog[svc_id].get("ports", [])
        if extra_ports and svc_id in extra_ports:
            ports = extra_ports[svc_id]
        for p in ports:
            hp = _parse_host_port(p)
            if hp:
                selection_ports.setdefault(hp, []).append(svc_id)

    conflicts: list[dict[str, Any]] = []

    # 1. Within-selection conflicts
    for port, services in selection_ports.items():
        if len(services) > 1:
            conflicts.append({
                "severity": "critical",
                "type": "selection_conflict",
                "port": port,
                "services": services,
                "message": f"Port {port} claimed by multiple selected services: {', '.join(services)}",
                "fix": f"Remove one of {', '.join(services)} from your selection, or change one of their host ports",
            })

    # 2. Running container conflicts
    if docker_client:
        running = get_running_port_map(docker_client)
        for port, services in selection_ports.items():
            if port in running:
                container_name = running[port]
                # Don't flag if the running container is one of the selected services
                # (it will be recreated)
                if container_name not in selected_services:
                    conflicts.append({
                        "severity": "warning",
                        "type": "running_conflict",
                        "port": port,
                        "services": services,
                        "running_container": container_name,
                        "message": f"Port {port} (used by {', '.join(services)}) is already bound by running container '{container_name}'",
                        "fix": f"Stop '{container_name}' before deploying, or change the host port for {', '.join(services)}",
                    })

    # 3. Host port already bound (non-Docker process)
    for port, services in selection_ports.items():
        if is_port_in_use(port):
            # Check if already flagged by running container check
            already_flagged = any(
                c["port"] == port and c["type"] == "running_conflict"
                for c in conflicts
            )
            if not already_flagged:
                conflicts.append({
                    "severity": "warning",
                    "type": "host_conflict",
                    "port": port,
                    "services": services,
                    "message": f"Port {port} (used by {', '.join(services)}) is already in use by another process on the host",
                    "fix": f"Find what's using port {port}: sudo ss -tlnp | grep {port}",
                })

    # Summary
    critical = [c for c in conflicts if c["severity"] == "critical"]
    warnings  = [c for c in conflicts if c["severity"] == "warning"]

    return {
        "ok": len(conflicts) == 0,
        "critical": len(critical),
        "warnings": len(warnings),
        "conflicts": conflicts,
        "port_map": {
            port: services
            for port, services in selection_ports.items()
        },
    }

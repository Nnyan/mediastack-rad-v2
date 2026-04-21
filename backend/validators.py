"""Config validation — runs before we let Docker touch anything.

The overhaul exists because we got burned by two failure modes in the
previous iteration: (1) a subtle YAML indent error that crashed Traefik
in a restart loop, and (2) a duplicate environment variable where the
empty version overrode the real one silently. Both would have been
caught in 50ms by these validators.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ValidationIssue:
    """A problem found during validation.

    `line` is None for file-level issues (e.g. missing file).
    `severity=error` stops the operation; `warning` is advisory.
    """
    severity: str  # "error" or "warning"
    message: str
    line: int | None = None
    context: str | None = None


# ---------------------------------------------------------------------------
# YAML validation
# ---------------------------------------------------------------------------


def validate_yaml_file(path: Path) -> list[ValidationIssue]:
    """Parse a YAML file and return any syntax or structural problems.

    Returns an empty list when the file is valid.
    """
    issues: list[ValidationIssue] = []

    if not path.exists():
        return [ValidationIssue("error", f"File not found: {path}")]

    try:
        text = path.read_text()
    except OSError as e:
        return [ValidationIssue("error", f"Cannot read {path}: {e}")]

    # Empty files parse to None — fine for acme.json, bad for compose.
    if not text.strip():
        return [ValidationIssue("warning", f"{path.name} is empty")]

    try:
        yaml.safe_load(text)
    except yaml.YAMLError as e:
        # PyYAML errors have a mark attribute with line/column info.
        line = getattr(getattr(e, "problem_mark", None), "line", None)
        line = line + 1 if line is not None else None  # 1-indexed for humans
        ctx = str(getattr(e, "problem", "") or "").strip() or str(e)
        issues.append(ValidationIssue("error", f"YAML parse error: {ctx}", line))

    return issues


def validate_compose_file(path: Path) -> list[ValidationIssue]:
    """Validate a docker-compose.yml beyond just YAML syntax.

    Catches:
      - duplicate environment keys within a single service (silent bug)
      - services referencing undefined networks
      - ports on services marked `network_mode: host`
      - missing container_name when multiple services share a host port
    """
    issues = validate_yaml_file(path)
    if any(i.severity == "error" for i in issues):
        return issues  # no point continuing if the YAML itself is broken

    text = path.read_text()
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return issues

    services = doc.get("services") or {}
    networks = set((doc.get("networks") or {}).keys())

    # --- duplicate env keys within a single service ---------------------
    # PyYAML silently merges duplicate keys, so we scan the raw text.
    # For each service block, find the `environment:` section and
    # collect every key we see. Duplicates → error.
    issues.extend(_scan_duplicate_env_keys(text))

    # --- host port collisions ------------------------------------------
    host_ports: dict[str, list[str]] = {}  # "80/tcp" -> [service names]
    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            continue

        # Services on host network shouldn't declare ports
        if svc.get("network_mode") == "host" and svc.get("ports"):
            issues.append(ValidationIssue(
                "warning",
                f"Service '{svc_name}' uses network_mode=host but also "
                f"declares ports; ports will be ignored.",
            ))

        for port_spec in svc.get("ports") or []:
            # ports can be strings ("80:80") or dicts (long-form).
            parsed = _parse_port(port_spec)
            if parsed:
                key = f"{parsed['host']}/{parsed['protocol']}"
                host_ports.setdefault(key, []).append(svc_name)

        # Check that declared networks exist
        for net in svc.get("networks") or []:
            if isinstance(net, str) and net not in networks:
                issues.append(ValidationIssue(
                    "error",
                    f"Service '{svc_name}' references undefined network "
                    f"'{net}'",
                ))

    for port_key, owners in host_ports.items():
        if len(owners) > 1:
            issues.append(ValidationIssue(
                "error",
                f"Host port {port_key} is claimed by multiple services: "
                f"{', '.join(owners)}",
            ))

    return issues


_SERVICE_HEADER = re.compile(r"^  (\w[\w-]*):\s*$")
_ENV_BLOCK_START = re.compile(r"^    environment:\s*$")
_ENV_KEY = re.compile(r"^      -?\s*(\w+)\s*[:=]")


def _scan_duplicate_env_keys(text: str) -> list[ValidationIssue]:
    """Walk the raw compose file and flag duplicate env keys per service.

    This is the exact failure mode that made us lose an hour today —
    a CF_DNS_API_TOKEN appeared twice, and the empty second copy won.
    """
    issues: list[ValidationIssue] = []
    current_service: str | None = None
    in_env_block = False
    seen_keys: dict[str, int] = {}  # key -> first line number

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Service header changes — reset env tracking.
        if _SERVICE_HEADER.match(line):
            current_service = _SERVICE_HEADER.match(line).group(1)
            in_env_block = False
            seen_keys = {}
            continue

        # Start of environment block inside a service.
        if current_service and _ENV_BLOCK_START.match(line):
            in_env_block = True
            seen_keys = {}
            continue

        # A line with less indentation ends the env block.
        if in_env_block and line.strip() and not line.startswith("      "):
            in_env_block = False
            seen_keys = {}

        if in_env_block:
            m = _ENV_KEY.match(line)
            if m:
                key = m.group(1)
                if key in seen_keys:
                    issues.append(ValidationIssue(
                        "error",
                        f"Duplicate environment key '{key}' in service "
                        f"'{current_service}' (first seen on line "
                        f"{seen_keys[key]}, again on line {lineno}). "
                        f"The second value silently wins — this caused "
                        f"our CF token issue.",
                        line=lineno,
                    ))
                else:
                    seen_keys[key] = lineno

    return issues


def _parse_port(spec: Any) -> dict | None:
    """Normalize a port spec to {'host': '80', 'container': 80, 'protocol': 'tcp'}."""
    if isinstance(spec, int):
        return {"host": str(spec), "container": spec, "protocol": "tcp"}

    if isinstance(spec, dict):
        # Long form: {target: 80, published: 80, protocol: tcp}
        return {
            "host": str(spec.get("published", "")),
            "container": spec.get("target"),
            "protocol": spec.get("protocol", "tcp"),
        }

    if isinstance(spec, str):
        # Short form: "80:80" or "80:80/tcp" or "127.0.0.1:80:80/tcp"
        proto = "tcp"
        if "/" in spec:
            spec, proto = spec.rsplit("/", 1)
        parts = spec.split(":")
        if len(parts) == 1:
            return {"host": parts[0], "container": int(parts[0]), "protocol": proto}
        if len(parts) >= 2:
            return {"host": parts[-2], "container": int(parts[-1]), "protocol": proto}

    return None


# ---------------------------------------------------------------------------
# Traefik-specific validation
# ---------------------------------------------------------------------------


def validate_traefik_yaml(path: Path) -> list[ValidationIssue]:
    """Validate traefik.yml against the structural requirements we care about.

    Traefik's own config parser will reject invalid YAML, but the failure
    mode is a crash loop that tends to eat logs. Catching it here means
    we can tell the user exactly what's wrong before they hit restart.
    """
    issues = validate_yaml_file(path)
    if any(i.severity == "error" for i in issues):
        return issues

    doc = yaml.safe_load(path.read_text()) or {}

    # entryPoints should exist and have at minimum web/websecure.
    entry = doc.get("entryPoints") or {}
    if not entry:
        issues.append(ValidationIssue(
            "warning",
            "traefik.yml has no entryPoints; Traefik will not accept traffic",
        ))
    else:
        if "websecure" not in entry:
            issues.append(ValidationIssue(
                "warning",
                "No 'websecure' entryPoint defined — HTTPS will not work",
            ))

    # certificatesResolvers → validate DNS challenge structure if present.
    resolvers = doc.get("certificatesResolvers") or {}
    for name, resolver in resolvers.items():
        acme = (resolver or {}).get("acme") or {}
        if not acme.get("email"):
            issues.append(ValidationIssue(
                "error",
                f"certResolver '{name}' is missing acme.email",
            ))

        dns = acme.get("dnsChallenge")
        if dns is not None:
            if not dns.get("provider"):
                issues.append(ValidationIssue(
                    "error",
                    f"certResolver '{name}' has dnsChallenge but no provider",
                ))
            # This is the setting that actually fixes propagation issues
            # for us — default 10s delay is too short for Cloudflare.
            delay = dns.get("delayBeforeCheck", 0)
            if delay < 30:
                issues.append(ValidationIssue(
                    "warning",
                    f"certResolver '{name}' has delayBeforeCheck={delay}s; "
                    f"values below 30s often cause propagation timeouts",
                ))

    return issues


# ---------------------------------------------------------------------------
# Environment variable checks
# ---------------------------------------------------------------------------


def validate_env_file(path: Path) -> list[ValidationIssue]:
    """Validate a .env file for duplicate keys and empty values.

    Duplicates are the higher-risk case — Docker Compose uses the last
    definition silently. Empty values are flagged as warnings because
    they're sometimes intentional.
    """
    if not path.exists():
        return []  # .env is optional

    issues: list[ValidationIssue] = []
    seen: dict[str, int] = {}
    empty: list[tuple[str, int]] = []

    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            issues.append(ValidationIssue(
                "error",
                f"Malformed line (no '=' sign): {stripped!r}",
                line=lineno,
            ))
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()

        if key in seen:
            issues.append(ValidationIssue(
                "error",
                f"Duplicate key '{key}' in .env (first on line {seen[key]}, "
                f"again on line {lineno}). The second value silently wins.",
                line=lineno,
            ))
        else:
            seen[key] = lineno

        if not value.strip() or value.strip() in ("''", '""'):
            empty.append((key, lineno))

    for key, lineno in empty:
        issues.append(ValidationIssue(
            "warning",
            f"Environment variable '{key}' is empty on line {lineno}",
            line=lineno,
        ))

    return issues

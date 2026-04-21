#!/usr/bin/env bash
#
# healthcheck.sh — pre-flight diagnostic for a MediaStack-RAD host.
#
# Run this from the host shell to verify the environment is healthy
# enough to deploy the stack. It does NOT depend on RAD being running.
#
# Checks:
#   - Docker CLI + daemon reachable
#   - Compose plugin installed
#   - Port 80, 443, 8090, 8081 availability
#   - acme.json permissions (if it exists)
#   - No ghost containers
#   - Stack compose file validity (if present)
#
# Usage:
#   ./healthcheck.sh [--stack-dir /path/to/mediacenter]

set -uo pipefail

STACK_DIR="${STACK_DIR:-/home/stack/mediacenter}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stack-dir) STACK_DIR="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# ---- Output helpers --------------------------------------------------------

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'
else
    G=""; R=""; Y=""; B=""; N=""
fi

pass=0
fail=0
warn=0

ok()   { echo "  ${G}✓${N} $*"; ((pass++)); }
err()  { echo "  ${R}✗${N} $*"; ((fail++)); }
wrn()  { echo "  ${Y}!${N} $*"; ((warn++)); }
head() { echo; echo "${B}$*${N}"; }

# ---- Docker ---------------------------------------------------------------

head "Docker"

if command -v docker >/dev/null 2>&1; then
    ok "docker CLI: $(docker --version | head -1)"
else
    err "docker CLI not installed"
    exit 1
fi

if docker info >/dev/null 2>&1; then
    ok "docker daemon reachable"
else
    err "cannot talk to docker daemon (permission / socket?)"
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    ok "compose plugin: $(docker compose version --short)"
else
    err "docker compose v2 plugin missing"
fi

# ---- Ports ---------------------------------------------------------------

head "Ports"

check_port() {
    local port="$1"
    local name="$2"
    if ss -tlnp 2>/dev/null | awk '{print $4}' | grep -qE ":${port}$"; then
        wrn "port $port ($name) is in use — confirm it's the right service"
    else
        ok "port $port ($name) is free"
    fi
}

check_port 80   "HTTP (Traefik)"
check_port 443  "HTTPS (Traefik)"
check_port 8081 "Traefik dashboard"
check_port 8090 "MediaStack-RAD"

# ---- Directories ---------------------------------------------------------

head "Stack directory: $STACK_DIR"

if [[ -d "$STACK_DIR" ]]; then
    ok "exists"
else
    wrn "does not exist yet — will be created on first deploy"
fi

COMPOSE="$STACK_DIR/docker-compose.yml"
if [[ -f "$COMPOSE" ]]; then
    if docker compose -f "$COMPOSE" config >/dev/null 2>&1; then
        ok "docker-compose.yml valid"
    else
        err "docker-compose.yml has errors — run: docker compose -f $COMPOSE config"
    fi
else
    wrn "no docker-compose.yml yet (generate via Stack Builder)"
fi

ACME="$STACK_DIR/config/traefik/letsencrypt/acme.json"
if [[ -f "$ACME" ]]; then
    mode=$(stat -c '%a' "$ACME")
    if [[ "$mode" == "600" ]]; then
        ok "acme.json permissions 0600"
    else
        err "acme.json is $mode — must be 600. Run: chmod 600 $ACME"
    fi
fi

# ---- Ghost containers ----------------------------------------------------

head "Ghost containers"

GHOSTS=$(docker ps -a --format '{{.Names}}\t{{.Status}}' | \
         awk -F'\t' '$2 !~ /Up/ && $1 ~ /^[0-9a-f]{12}_/ {print $1}')

if [[ -z "$GHOSTS" ]]; then
    ok "no ghost containers"
else
    echo "$GHOSTS" | while read -r name; do
        err "ghost container: $name — remove with: docker rm -f $name"
    done
fi

# ---- Summary -------------------------------------------------------------

head "Summary"
echo "  ${G}$pass passed${N}, ${Y}$warn warnings${N}, ${R}$fail failed${N}"
echo

if [[ "$fail" -gt 0 ]]; then
    exit 1
fi

#!/bin/sh
set -e

SOCKET="/var/run/docker.sock"
if [ -S "$SOCKET" ]; then
    GID=$(stat -c '%g' "$SOCKET" 2>/dev/null || echo "")
    if [ -n "$GID" ] && [ "$GID" != "0" ]; then
        groupadd -g "$GID" -f sockdocker 2>/dev/null || true
        usermod -aG sockdocker rad 2>/dev/null || true
    fi
fi

RAD_UID=$(id -u rad)
RAD_GID=$(id -g rad)
STACK_DIR="${RAD_STACK_DIR:-/compose}"

# RAD writes docker-compose.yml, .env, and Traefik config into the mounted
# stack directory. Host-created files can be owned by root/another UID, so fix
# the writable paths while still running as root, before dropping privileges.
if [ -n "$STACK_DIR" ]; then
    mkdir -p "$STACK_DIR" 2>/dev/null || true
    chown "$RAD_UID:$RAD_GID" "$STACK_DIR" 2>/dev/null || true
    chmod u+rwx "$STACK_DIR" 2>/dev/null || true

    for path in \
        "$STACK_DIR/.env" \
        "$STACK_DIR/docker-compose.yml" \
        "$STACK_DIR/config" \
        "$STACK_DIR/config/traefik"
    do
        if [ -e "$path" ]; then
            chown -R "$RAD_UID:$RAD_GID" "$path" 2>/dev/null || true
            chmod -R u+rwX "$path" 2>/dev/null || true
        fi
    done
fi

# Drop privileges to the 'rad' user and exec the CMD.
# Uses Python since it's guaranteed to be present in this image
# and handles supplementary group membership correctly.
exec python3 -c "
import os, sys
os.setgroups(os.getgrouplist('rad', $RAD_GID))
os.setgid($RAD_GID)
os.setuid($RAD_UID)
os.execvp(sys.argv[1], sys.argv[1:])
" "$@"

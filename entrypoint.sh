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

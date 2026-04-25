#!/usr/bin/env bash
#
# cleanup-acme.sh — remove stale _acme-challenge TXT records from Cloudflare.
#
# Let's Encrypt's DNS-01 challenge creates temporary TXT records with
# distinctive names like `_acme-challenge.example.com`. When Traefik
# times out, it sometimes leaves these lying around. Subsequent cert
# requests then see both the new record (from the current attempt) and
# the stale one (from a prior attempt), and the nameserver may return
# the wrong one — causing propagation checks to fail indefinitely.
#
# This script lists and optionally deletes every _acme-challenge TXT
# record on a given zone.
#
# Usage:
#   CF_TOKEN=... ZONE=example.com ./cleanup-acme.sh [--delete]
#
#   --delete    actually delete them. Without it, just lists.

set -uo pipefail

CF_TOKEN="${CF_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
ZONE="${ZONE:-}"
DELETE="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --delete) DELETE="true"; shift ;;
        --help|-h)
            grep -E '^#' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$CF_TOKEN" ]]; then
    echo "error: CF_TOKEN (or CLOUDFLARE_API_TOKEN) must be set" >&2
    exit 1
fi
if [[ -z "$ZONE" ]]; then
    echo "error: ZONE must be set (e.g. ZONE=example.com)" >&2
    exit 1
fi

API="https://api.cloudflare.com/client/v4"
AUTH="Authorization: Bearer $CF_TOKEN"

# Resolve zone name → zone id
ZONE_ID=$(curl -fsS -H "$AUTH" "$API/zones?name=$ZONE" | \
          python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["result"][0]["id"])')

if [[ -z "$ZONE_ID" || "$ZONE_ID" == "null" ]]; then
    echo "error: could not resolve zone id for $ZONE" >&2
    exit 1
fi

echo "Zone: $ZONE ($ZONE_ID)"

# Get all TXT records matching _acme-challenge*
RECORDS=$(curl -fsS -H "$AUTH" \
          "$API/zones/$ZONE_ID/dns_records?type=TXT&per_page=200" | \
          python3 -c '
import json, sys
d = json.load(sys.stdin)
for r in d.get("result", []):
    if r.get("name", "").startswith("_acme-challenge"):
        print(f"{r[\"id\"]}\t{r[\"name\"]}\t{r[\"content\"][:40]}")
')

if [[ -z "$RECORDS" ]]; then
    echo "No _acme-challenge TXT records found. Nothing to do."
    exit 0
fi

echo "Found _acme-challenge records:"
echo "$RECORDS" | awk -F'\t' '{printf "  %-40s %s...\n", $2, $3}'

if [[ "$DELETE" != "true" ]]; then
    echo
    echo "Re-run with --delete to remove them."
    exit 0
fi

echo
echo "Deleting..."
FAIL=0
while IFS=$'\t' read -r id name content; do
    # Temporarily disable exit-on-error so a failed delete doesn't abort
    # the loop — we want to attempt all records and report failures at the end.
    if curl -fsS -X DELETE -H "${AUTH}" \
         "${API}/zones/${ZONE_ID}/dns_records/${id}" >/dev/null 2>&1; then
        echo "  deleted ${name}"
    else
        echo "  FAILED to delete ${name}" >&2
        FAIL=1
    fi
done <<< "$RECORDS"

if [[ "$FAIL" -ne 0 ]]; then
    echo "Some records could not be deleted. Check your token permissions." >&2
    exit 1
fi

echo "Done."

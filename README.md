# MediaStack-RAD v2

A self-hosted dashboard for managing a home media server stack — Plex, Sonarr, Radarr, Prowlarr, and friends — running in Docker with automatic HTTPS via Traefik.

[![Build](https://github.com/nnyan/mediastack-rad-v2/actions/workflows/publish.yml/badge.svg)](https://github.com/nnyan/mediastack-rad-v2/actions/workflows/publish.yml)
[![Image](https://ghcr-badge.egpl.dev/nnyan/mediastack-rad-v2/size)](https://ghcr.io/nnyan/mediastack-rad-v2)

---

## What it does

- **Container dashboard** — live CPU/memory/network stats, start/stop/restart/remove, logs, bulk operations
- **Stack Builder** — pick services from a catalog, fill in domain + Cloudflare token, click Deploy — your `docker-compose.yml` is generated, validated, and brought up
- **Traefik management** — shows all active routes and cert status; includes cert reset and Traefik restart buttons
- **Health checker** — background system that runs 9 checks every 30 seconds and surfaces issues in real-time: Docker connectivity, compose file validity, duplicate env vars, ghost containers, port conflicts, ACME cert permissions, Cloudflare token, network isolation, Traefik reachability
- **Setup checklist** — a live to-do list that checks itself off as the system detects completion

---

## Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/nnyan/mediastack-rad-v2/main/install.sh | bash
```

Then open `http://<your-server-ip>:8090`.

## Opencode workflow (local)

`MODEL_BY_TASK.md` documents a model-by-task policy for Opencode. A small wrapper
command is available as `octask`.

```bash
chmod +x ./octask
octask quick "Fix a small typo"
octask standard "Refactor form validation"
octask critical "Adjust deploy-blocking authentication flow"
```

`octask` defaults to the standard tier when no tier is provided:

```bash
octask "Generate a patch for the requested task"
```

If your shell path does not include the repo, run with `./` from the repo root.

The installer:
1. Verifies prerequisites (Docker, Compose plugin)
2. Creates the stack directory at `/home/stack/mediacenter`
3. Creates the `mediastack` Docker network
4. Writes a `docker-compose.yml` for RAD
5. Pulls the image and starts RAD
6. Runs a post-install health check

Customize via environment variables:

```bash
STACK_DIR=/opt/mediacenter RAD_PORT=8090 bash install.sh
```

---

## Manual setup

```bash
# 1. Create the Docker network
docker network create mediastack

# 2. Create the stack directory
mkdir -p /home/stack/mediacenter/config/traefik/letsencrypt
touch /home/stack/mediacenter/config/traefik/letsencrypt/acme.json
chmod 600 /home/stack/mediacenter/config/traefik/letsencrypt/acme.json

# 3. Create a compose file for RAD
mkdir -p /home/stack/msrad
cat > /home/stack/msrad/docker-compose.yml <<'EOF'
services:
  mediastack-rad:
    image: ghcr.io/nnyan/mediastack-rad-v2:latest
    container_name: mediastack-rad
    restart: unless-stopped
    ports:
      - "8090:8090"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /home/stack/mediacenter:/compose
    environment:
      RAD_STACK_DIR: /compose
      RAD_TRAEFIK_DIR: /compose/config/traefik
    networks:
      - mediastack
networks:
  mediastack:
    name: mediastack
    external: true
EOF

# 4. Start RAD
docker compose -f /home/stack/msrad/docker-compose.yml up -d
```

---

## Configuring your stack

1. **Open the Stack Builder tab** and pick your services
2. Set your domain (e.g. `example.com`) — apps are served as `sonarr.example.com`
3. Set your Cloudflare API token (see [Creating a Cloudflare API token](#creating-a-cloudflare-api-token))
4. Set your config root and media root paths
5. Click **Preview** to review the generated compose YAML
6. Click **Deploy Stack** to write the file and run `docker compose up -d`
7. Follow the **Checklist** tab for remaining setup steps

When you generate or deploy, RAD now shows a quick token-source check in the output
area so you can confirm each Cloudflare secret is coming from the current request
or from `.env`.

If a domain is already configured in your current stack (for example in an existing
Traefik route or `TINYAUTH_APPURL`), the Builder Core settings domain field defaults
to that value when left empty.

### Custom app routing

Custom apps added in Stack Builder are merged as-is into the generated compose.
To make them accessible through Traefik automatically, the generator now:

- Adds Traefik labels automatically when `domain` is set
- Uses the first declared port mapping to infer the container web port
- Uses `container_name` (if present) for the public hostname; otherwise it uses
  the service key
- Applies the same Tinyauth two-router pattern as catalog services when Tinyauth is
  enabled

Example: a custom service named `mediastack` with `container_name: mediastack`
and `ports: ["8090:8090"]` will get a router host `mediastack.<your-domain>`.

If you need full control (advanced auth/rule/service/path behavior), add your
own Traefik labels explicitly in the custom YAML. If any `traefik.*` label is
present, the auto-labeler is skipped.

### Creating a Cloudflare API token

1. Go to [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click **Create Token**
3. Use the **Edit zone DNS** template
4. Under **Zone Resources** → Include → Specific zone → your domain
5. Click **Continue to summary** → **Create Token**
6. Copy the token — it only appears once

The token needs these permissions:
- Zone → **DNS** → Edit
- Zone → **Zone** → Read

### External access

You have two options:

**Option A: Cloudflare Tunnel (recommended, no port forwarding)**

Include `cloudflared` in your stack selection. After deploy, go to:
[one.dash.cloudflare.com](https://one.dash.cloudflare.com) → Networks → Tunnels → your tunnel → Public Hostnames

Add a hostname for each service:
- Subdomain: `sonarr`, Domain: `example.com`, Service: `https://<server-ip>:443`
- Subdomain: `radarr`, Domain: `example.com`, Service: `https://<server-ip>:443`
- In Tunnel settings, use **No TLS Verify = on** so Cloudflare trusts Traefik’s
  cert chain and internal HTTPS forwarding.
- (repeat for each service)

This routes all traffic through Traefik so catalog auth (for example, Tinyauth)
and HTTPS certificates stay in one place.

Cloudflare creates the DNS records automatically. Your home IP stays private.

**Option B: Direct port forwarding**

Add DNS A records in Cloudflare pointing at your public IP (DNS Only — grey cloud), then forward ports 80 and 443 from your router to your server.

---

## Troubleshooting

All of these were hit during real testing and are now caught by the health checker.

### Traefik: `client version 1.24 is too old`

The Docker API version negotiation issue. **Fix:** use `traefik:latest`, not a pinned version, and mount the host socket directly — not via `tecnativa/docker-socket-proxy` which has a version negotiation bug.

### Traefik: `propagation: time limit exceeded`

DNS-01 challenge times out before Cloudflare propagates the TXT record. **Fix:**

1. Verify `LEGO_DNS_TIMEOUT: "300"` is set in Traefik's environment in your compose file
2. Verify `delayBeforeCheck: 60` is set under `dnsChallenge` in `traefik.yml`
3. Check for stale `_acme-challenge` TXT records in Cloudflare DNS — delete them all
4. Use the Traefik cleanup tools in the Traefik tab of RAD

The root cause during our setup: a **duplicate `CF_DNS_API_TOKEN` env var** where the second (empty) copy overrode the real token silently. The health checker now catches this.

### `CF_DNS_API_TOKEN` is wrong inside Traefik

Verify what's actually in the running container:

```bash
docker exec traefik printenv CF_DNS_API_TOKEN
```

Check for duplicates in your compose file:

```bash
grep -n "CF_DNS_API_TOKEN" /home/stack/mediacenter/docker-compose.yml
```

There should be exactly one line. Docker silently uses the **last** definition when there are duplicates.

### Ghost containers blocking deploys

```
Error: Conflict. The container name "/sabnzbd" is already in use
```

A failed recreate leaves a renamed copy. Fix:

```bash
docker container prune -f
docker compose -f /home/stack/mediacenter/docker-compose.yml up -d
```

The health checker flags ghost containers automatically and offers auto-removal.

### Readarr removed from catalog but old UI config still selected

If you upgraded from an older version that had `readarr`, that stale key may still
exist in browser localStorage. RAD now handles this safely:

- generation/deploy still succeeds,
- a warning is shown: `Service 'readarr' is no longer supported and will be ignored`, and
- no `readarr` service is added to generated compose output.

This keeps existing users' deployments intact without forcing immediate local
state cleanup.

### Permission denied while writing compose files at runtime

If deploy returns:

```text
Permission denied while writing compose files at /compose
```

that means `RAD_STACK_DIR` / `RAD_TRAEFIK_DIR` are mounted read-only or point to
an unwritable path. Set them to writable host paths in the RAD container:

```bash
RAD_STACK_DIR=/home/stack/msrad
RAD_TRAEFIK_DIR=/home/stack/msrad/traefik
```

Then restart RAD and confirm with:

```bash
curl -s http://127.0.0.1:8090/api/settings/meta
```
`stack_dir_writable` should report `true`.

### Traefik `yaml: line N: mapping values are not allowed in this context`

Indentation error in `traefik.yml`. The correct indent for `dnsChallenge` options is:

```yaml
dnsChallenge:
  provider: cloudflare      # ← 10 spaces from line start
  delayBeforeCheck: 60      # ← 10 spaces from line start
  resolvers:                # ← 10 spaces from line start
    - "1.1.1.1:53"          # ← 12 spaces from line start
```

Use the stack generator's Traefik config output — it's always correct.

### Traefik routes registered but cert not issued (`pending` in RAD)

The container has Traefik labels but Traefik can't route to it:

1. Check that the container and Traefik are on the same Docker network:
   ```bash
   docker inspect traefik --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
   docker inspect sonarr --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
   ```
   Both should show `mediastack`.

2. Check the Traefik API for the router's status:
   ```bash
   curl -s http://localhost:8081/api/http/routers | python3 -m json.tool | grep -A5 sonarr
   ```

3. Confirm `traefik.enable=true` label is on the container:
   ```bash
   docker inspect sonarr --format '{{range $k,$v := .Config.Labels}}{{$k}}={{$v}}\n{{end}}' | grep traefik
   ```

### acme.json permissions

```bash
chmod 600 /home/stack/mediacenter/config/traefik/letsencrypt/acme.json
docker restart traefik
```

### SPA returns HTML from API endpoints

This is the SPA catch-all route ordering bug from the original build. Fixed in v2 by construction — the catch-all is registered last and an import-time assertion enforces it. If you see HTML coming from `/api/` routes, you're running a broken custom image.

---

## Environment variables

### RAD container

| Variable | Default | Description |
|---|---|---|
| `RAD_STACK_DIR` | `/compose` | Where the managed stack's compose file lives |
| `RAD_TRAEFIK_DIR` | `/compose/config/traefik` | Traefik config + cert directory |
| `RAD_DOCKER_SOCKET` | `unix:///var/run/docker.sock` | Docker socket path |
| `RAD_BIND_HOST` | `0.0.0.0` | Interface to bind the HTTP server to |
| `RAD_BIND_PORT` | `8090` | Port to listen on |
| `RAD_HEALTH_INTERVAL` | `30` | Background health check interval (seconds) |
| `RAD_STATS_INTERVAL` | `2.0` | WebSocket stats push interval (seconds) |
| `RAD_COMPOSE_UP_TIMEOUT` | `600` | Seconds to wait for `docker compose up -d` before returning timeout |

### Traefik container (in the managed stack)

| Variable | Required | Description |
|---|---|---|
| `CF_DNS_API_TOKEN` | For DNS-01 | Your Cloudflare API token. Only ONE `CF_DNS_API_TOKEN` line — duplicate keys override each other silently. |
| `LEGO_DNS_TIMEOUT` | Recommended | Set to `300`. Default is too short for Cloudflare propagation. |

---

## Architecture

```
                         host
 ┌──────────────────────────────────────────────────────────┐
 │                                                          │
 │   /var/run/docker.sock                                   │
 │          │                                               │
 │   ┌──────▼──────┐    network: mediastack                 │
 │   │ mediastack- │◄──────────────────────────────────┐   │
 │   │    rad      │                                   │   │
 │   │  :8090      │                                   │   │
 │   └─────────────┘                                   │   │
 │                                                     │   │
 │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────┐ │   │
 │   │ traefik │  │  sonarr │  │  radarr │  │  ...  │─┘   │
 │   │:80/:443 │  │  :8989  │  │  :7878  │  │       │     │
 │   └────┬────┘  └─────────┘  └─────────┘  └───────┘     │
 │        │                                                 │
 └────────┼─────────────────────────────────────────────────┘
          │ public
     sonarr.example.com → HTTPS → Traefik → sonarr:8989
```

RAD manages the mediacenter stack through the Docker socket. Traefik sits in front of all services and handles HTTPS automatically via Let's Encrypt DNS-01 challenges against Cloudflare.

---

## Development

```bash
# Clone
git clone https://github.com/nnyan/mediastack-rad-v2
cd mediastack-rad-v2

# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8090

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # Vite dev server on :5173, proxies /api and /ws to :8090
```

---

## License

MIT — see LICENSE.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

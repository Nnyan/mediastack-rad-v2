# MediaStack-RAD v2

A real-time Docker container dashboard for your self-hosted media stack.
Built with **FastAPI + docker-py** (backend) and **Vue 3** (frontend).

---

## Features

- **Live container dashboard** — real CPU, memory, and status via WebSocket (2s updates)
- **Start / stop / restart** containers from the UI
- **Log viewer** — tail 50–500 lines per container
- **Troubleshooter** — analyses logs and container state, returns ranked findings with step-by-step remediation
- **Stack health** — validates API keys and network connectivity between mediastack services
- **Traefik & HTTPS manager** — set a domain, choose HTTP-01 or wildcard certs, auto-patch labels into your compose file and recreate containers in one click
- **Compose import** — paste a `docker-compose.yml` or give a GitHub URL to preview services
- **Category grouping** — group containers by type, move any container to a different group
- **Dark / light theme** — persisted in browser

---

## Requirements

- Docker Engine 24+ with the Compose v2 plugin (`docker compose`, not `docker-compose`)
- Your media stack managed by a `docker-compose.yml` file on the host
- Port 8090 (or your chosen port) reachable on the LAN

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/Nnyan/mediastack-rad-v2.git
cd mediastack-rad-v2
```

### 2. Configure

```bash
cp .env.example .env
nano .env
```

The important settings:

```env
# Port the dashboard listens on
PORT=8090

# Path on the HOST to your media stack compose folder
# (mounted at /compose inside the container — needed for Traefik auto-apply)
COMPOSE_DIR=/opt/mediastack

# Only change if your file has a non-standard name
COMPOSE_FILE_PATH=/compose/docker-compose.yml

# If your stack containers are on an existing Docker network:
DOCKER_NETWORK=mediastack
NETWORK_EXTERNAL=true
```

> **COMPOSE_DIR is optional.** If you only want monitoring and not the
> Traefik auto-apply feature, leave it pointing anywhere or leave the default.
> Everything else works without it.

### 3. Build and start

```bash
docker compose up -d --build
```

First build takes 2–4 minutes — pulls Node 20, Docker CLI, and Python 3.12 base images,
compiles the Vue frontend, and installs Python dependencies.

### 4. Open the dashboard

```
http://your-server-ip:8090
```

---

## Useful commands

```bash
# Check it started correctly
docker compose ps
docker compose logs -f

# Stop
docker compose down

# Pull latest code and rebuild
git pull && docker compose up -d --build
```

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8090` | Host port for the dashboard |
| `COMPOSE_DIR` | `/opt/mediastack` | Host path to your stack compose folder |
| `COMPOSE_FILE_PATH` | `/compose/docker-compose.yml` | Compose file path inside the container |
| `TRAEFIK_ENABLE` | `false` | Activate Traefik labels on the RAD container itself |
| `TRAEFIK_HOST` | — | Traefik hostname for RAD (e.g. `rad.yourdomain.com`) |
| `DOCKER_NETWORK` | `mediastack-rad` | Docker network for the RAD container |
| `NETWORK_EXTERNAL` | `false` | `true` if the network already exists |

---

## Joining your existing mediastack network

If your media stack containers are on a network called `mediastack`:

```env
DOCKER_NETWORK=mediastack
NETWORK_EXTERNAL=true
```

This lets RAD reach other containers by name for the stack health checks and Traefik API verification.

---

## Traefik & HTTPS

Open the **Traefik** tab. Two cert modes:

**Per-app certs (HTTP-01)** — simplest. Each service gets its own Let's Encrypt cert.
Port 80 must be reachable from the internet for the ACME challenge.

**Wildcard cert (DNS-01)** — one `*.yourdomain.com` cert covers everything.
Requires Traefik configured with DNS provider credentials (Cloudflare, Route53, etc.).

Set your domain and click **Save config**. Then for each container:

1. Click **Preview changes** — see exactly which labels will be added (no writes, safe to run)
2. Click **Apply & recreate** — patches the compose file (backs up to `.bak` first), then runs:
   ```
   docker compose up -d --no-deps <service>
   ```
3. Watch the output in the terminal panel
4. If anything goes wrong, click **Restore** to put the original compose file back

**Apply all** in the left panel does every container at once with a confirmation step first.

For the apply feature to work, `COMPOSE_DIR` must point at your stack folder and the Docker socket must be writable. The three readiness pills at the top of the Traefik page confirm this at a glance.

---

## Docker socket access

The socket is mounted **without** `:ro` so `docker compose up` can run as a subprocess.
If you only need monitoring, add `:ro` back in `docker-compose.yml`:

```yaml
- /var/run/docker.sock:/var/run/docker.sock:ro
```

The apply buttons will detect this and disable themselves with a clear message.

---

## Security

The dashboard has **no built-in authentication**. Do not expose port 8090 to the internet.

Recommended options:
- **Traefik + Authentik or Authelia** — use the Middleware field in the Traefik config panel to add SSO to every route in one step
- **Tailscale or WireGuard** — access only over VPN, no port forwarding needed
- **Traefik basic auth middleware** — lightweight option for a single user

---

## Architecture

```
Browser ── HTTP + WebSocket ──▶ FastAPI (uvicorn :8090)
                                    │
                    ┌───────────────┼──────────────────┐
                    │               │                  │
              Serves Vue SPA    docker-py SDK     subprocess:
              from /static      (real container   docker compose
                                 data via socket)  up -d --no-deps
                                    │
                            /var/run/docker.sock
                                    │
                        ┌───────────┴──────────┐
                        │                      │
                  Container API          /compose/*.yml
                  (list/start/stop/      (host file, mounted
                   logs/stats)            read-write, patched
                                          by apply.py)
```

Single container — no nginx, no separate process.

---

## API reference

Full interactive docs at `http://your-server-ip:8090/docs`

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/docker/info` | Host version, CPU, RAM, container counts |
| GET | `/api/containers` | List all containers |
| GET | `/api/containers/{id}` | Detail + stats |
| POST | `/api/containers/{id}/start` | Start |
| POST | `/api/containers/{id}/stop` | Stop |
| POST | `/api/containers/{id}/restart` | Restart |
| GET | `/api/containers/{id}/logs?tail=100` | Tail logs |
| GET | `/api/containers/{id}/stats` | CPU + memory snapshot |
| GET | `/api/containers/{id}/troubleshoot` | Diagnose with remediation steps |
| GET | `/api/networks` | List networks |
| GET | `/api/images` | List images |
| GET | `/api/stack/health` | API key + network validation |
| GET/POST | `/api/categories` | Load / save category assignments |
| POST | `/api/compose/parse` | Parse pasted YAML |
| POST | `/api/compose/github` | Fetch and parse compose from GitHub |
| GET/POST | `/api/traefik/config` | Load / save Traefik domain config |
| GET | `/api/traefik/status` | Traefik state + per-container routing |
| GET | `/api/traefik/system` | Compose file / docker CLI / socket check |
| GET | `/api/traefik/compose` | Full compose snippet for all containers |
| POST | `/api/traefik/apply/{id}` | Patch compose + recreate one container |
| POST | `/api/traefik/apply-all` | Patch all + `docker compose up -d` |
| POST | `/api/traefik/restore/{id}` | Restore `.bak` backup |
| WS | `/ws/stats` | Live stats stream, all running containers, 2s interval |

---

## Local development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8090

# Frontend (second terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173 — proxies /api and /ws to :8090
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn, docker-py, websockets, ruamel.yaml |
| Frontend | Vue 3, Vue Router, Vite 6 |
| Styling | Plain CSS — dark + light theme, zero CSS framework |
| Build | 3-stage Docker build: node:20-alpine → docker:27-cli → python:3.12-slim |

---

## License

MIT

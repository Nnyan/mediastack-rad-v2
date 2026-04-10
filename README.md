# MediaStack-RAD v2

A real-time Docker container dashboard for your self-hosted media stack.  
Built with **FastAPI + docker-py** (backend) and **Vue 3** (frontend) — no fake data, no simulations.

## What it does

- Lists all Docker containers on the host with live status
- Streams real CPU and memory stats via WebSocket (updates every 2 seconds)
- Start, stop, and restart containers from the UI
- Tail container logs (50 / 100 / 200 / 500 lines)
- Shows published ports, networks, labels, and restart policy
- Search and filter by name, image, or status
- Docker host info bar (version, total CPU/RAM, running/stopped counts)
- Optional Traefik reverse proxy integration

## Quick start

```bash
git clone https://github.com/Nnyan/mediastack-rad-v2.git
cd mediastack-rad-v2
cp .env.example .env
docker compose up -d --build
```

Open **http://your-server-ip:8090**

Build takes 2–3 minutes on first run (downloads Node + Python base images, installs deps, compiles Vue).

## Architecture

```
Browser
  │  HTTP + WebSocket
  ▼
FastAPI (uvicorn, port 8090)
  │  Serves built Vue SPA from /static
  │  REST  /api/containers  /api/docker/info  /api/networks  /api/images
  │  WS    /ws/stats  (live CPU + memory, every 2s)
  ▼
Docker SDK (docker-py)
  │
  ▼
/var/run/docker.sock  (mounted read-only)
```

Single container, no nginx, no separate frontend server.  
The Vue app is compiled at build time and served as static files by FastAPI.

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/docker/info` | Docker host info |
| GET | `/api/containers` | List all containers |
| GET | `/api/containers/{id}` | Container detail + stats |
| POST | `/api/containers/{id}/start` | Start container |
| POST | `/api/containers/{id}/stop` | Stop container |
| POST | `/api/containers/{id}/restart` | Restart container |
| GET | `/api/containers/{id}/logs?tail=100` | Tail logs |
| GET | `/api/containers/{id}/stats` | One-shot CPU/mem stats |
| GET | `/api/networks` | List networks |
| GET | `/api/images` | List images |
| WS | `/ws/stats` | Live stats stream (JSON, 2s interval) |

Interactive API docs available at **http://your-server-ip:8090/docs**

## Configuration

Copy `.env.example` to `.env` and edit:

```env
# Host port (default 8090)
PORT=8090

# Traefik reverse proxy (optional)
TRAEFIK_ENABLE=false
TRAEFIK_HOST=mediastack-rad.yourdomain.com

# Attach to existing Docker network (e.g. your mediastack network)
DOCKER_NETWORK=mediastack-rad
NETWORK_EXTERNAL=false
```

### Traefik integration

```env
TRAEFIK_ENABLE=true
TRAEFIK_HOST=rad.yourdomain.com
DOCKER_NETWORK=mediastack
NETWORK_EXTERNAL=true
```

Then: `docker compose up -d --build`

## Local development

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8090
```

**Frontend** (in a second terminal):
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 — proxies /api and /ws to backend
```

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, uvicorn, docker-py, WebSockets |
| Frontend | Vue 3, Vue Router, Vite 6 |
| Styling | Plain CSS (dark theme, ~400 lines, zero dependencies) |
| Container | python:3.12-slim (~160MB final image) |

## Security notes

- Docker socket is mounted **read-only** (`ro`). The backend cannot create or delete containers — only list, start, stop, restart, and read logs/stats.
- The app has no authentication. **Do not expose port 8090 to the internet directly** — use Traefik + Authentik or a VPN.

## License

MIT

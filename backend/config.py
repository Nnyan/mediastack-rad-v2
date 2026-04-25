"""Runtime configuration loaded from environment variables.

All paths and behavior knobs live here so other modules don't sprinkle
os.environ reads throughout the codebase. Defaults are chosen for a
typical single-host deployment on Debian/Ubuntu.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Where the managed stack's docker-compose.yml lives on the host.
    # Mounted into RAD as a volume. The generator writes to this path.
    stack_dir: Path

    # Where Traefik config + certs live on the host.
    # Traefik mounts /letsencrypt and /etc/traefik from here.
    traefik_dir: Path

    # Docker socket path inside the RAD container.
    docker_socket: str

    # Host address to bind the FastAPI app to inside the container.
    bind_host: str

    # Port the FastAPI app listens on inside the container.
    bind_port: int

    # How often the background health checker re-runs (seconds).
    health_interval: int

    # How often container stats are sampled for the WebSocket feed.
    stats_interval: float

    # Where built frontend assets live inside the container.
    # The Dockerfile copies the Vite build output here.
    static_dir: Path

    # Optional API key for bearer-token authentication.
    # When set, all /api/* and /ws/* requests require the header
    # "Authorization: Bearer <key>". When empty (default), auth is disabled
    # for the home-lab LAN-only use case.
    api_key: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            stack_dir=Path(os.environ.get("RAD_STACK_DIR", "/compose")),
            traefik_dir=Path(
                os.environ.get("RAD_TRAEFIK_DIR", "/compose/config/traefik")
            ),
            docker_socket=os.environ.get(
                "RAD_DOCKER_SOCKET", "unix:///var/run/docker.sock"
            ),
            bind_host=os.environ.get("RAD_BIND_HOST", "0.0.0.0"),
            bind_port=int(os.environ.get("RAD_BIND_PORT", "8090")),
            health_interval=int(os.environ.get("RAD_HEALTH_INTERVAL", "30")),
            stats_interval=float(os.environ.get("RAD_STATS_INTERVAL", "2.0")),
            static_dir=Path(os.environ.get("RAD_STATIC_DIR", "/app/static")),
            api_key=os.environ.get("RAD_API_KEY", ""),
        )


config = Config.from_env()

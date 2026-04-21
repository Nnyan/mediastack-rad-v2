# syntax=docker/dockerfile:1.7
#
# MediaStack-RAD v2 — single-container build.
#
# Stage 1: build the Vue frontend with Vite.
# Stage 2: build the Python venv with all dependencies.
# Stage 3: runtime image — Python + built frontend assets, no build tools.
#
# The wildcard `COPY backend/*.py` in the runtime stage is intentional:
# in our v1 we listed each module by name and silently broke the image
# every time a new backend file was added. A wildcard makes the
# manifest self-maintaining.

# ---------------------------------------------------------------------------
# Stage 1: frontend build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend

# Install deps first so `npm ci` is cached when only source changes
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python deps
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS pybuild
WORKDIR /build

# Install build tools only for compiling wheels that have no manylinux build
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 3: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install Docker CLI + Compose plugin from Docker's official apt repo.
# The default debian:slim repos don't carry docker-compose-plugin.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/debian \
       $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
        docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Python runtime dependencies from the build stage
COPY --from=pybuild /install /usr/local

# Backend — WILDCARD COPY. Every *.py in backend/ comes along. This is
# the exact fix for the "forgot to copy the new module" bug in v1.
COPY backend/*.py /app/backend/

# Frontend built assets from stage 1
COPY --from=frontend /app/frontend/dist /app/static/

# The FastAPI app expects static files at /app/static/ and source at
# /app/backend/. Both are configurable via env vars — see config.py.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RAD_STATIC_DIR=/app/static \
    RAD_BIND_HOST=0.0.0.0 \
    RAD_BIND_PORT=8090

EXPOSE 8090

# Built-in healthcheck — the /api/version endpoint is cheap and proves
# both the app is running and the routes are wired correctly.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8090/api/version || exit 1

# uvicorn runs the FastAPI app directly. No nginx, no gunicorn —
# the app serves both API and static files in one process.
CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8090", \
     "--no-access-log", "--log-level", "info"]

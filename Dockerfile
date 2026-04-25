# syntax=docker/dockerfile:1.7
#
# MediaStack-RAD v2 — single-container build.
#
# CI OPTIMIZATION: The frontend is built natively on the GitHub Actions
# runner (fast, no QEMU) and the dist/ is committed to the build context
# via upload/download artifact. The Dockerfile detects the pre-built dist/
# and skips npm run build — cutting multi-arch build time from ~60min to ~5min.
#
# For local builds: if frontend/dist/ doesn't exist, it's built here as usual.

# ---------------------------------------------------------------------------
# Stage 1: frontend
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./

# Only run npm install+build if dist/ was NOT pre-built by CI.
# CI passes the pre-built dist/ in the build context so this stage
# just copies it without running Node.
COPY frontend/ ./
RUN if [ ! -f dist/index.html ]; then \
      npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund; \
      npm run build; \
    else \
      echo "Using pre-built frontend dist/"; \
    fi

# ---------------------------------------------------------------------------
# Stage 2: Python deps
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS pybuild
WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 3: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

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

COPY --from=pybuild /install /usr/local
COPY backend/*.py /app/backend/
COPY --from=frontend /app/frontend/dist /app/static/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RAD_STATIC_DIR=/app/static \
    RAD_BIND_HOST=0.0.0.0 \
    RAD_BIND_PORT=8090

# Run as a non-root user. The Docker socket is still mounted at runtime
# (required for container management) but the process itself does not
# run as UID 0. The user is added to the 'docker' group so it can access
# the socket without needing root.
RUN groupadd -r docker || true \
    && groupadd -r rad \
    && useradd -r -g rad -G docker rad \
    && chown -R rad:rad /app

USER rad

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8090/api/version || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8090", \
     "--no-access-log", "--log-level", "info"]

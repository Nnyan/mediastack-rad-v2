# ── Stage 1: Build Vue frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install --ignore-scripts

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Docker CLI (for compose auto-apply feature) ──────────────────────
FROM docker:27-cli AS docker-cli

# ── Stage 3: Python backend + serve frontend ──────────────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

COPY --from=docker-cli /usr/local/bin/docker                  /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins  /usr/local/libexec/docker/cli-plugins

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend modules
COPY backend/main.py \
     backend/troubleshoot.py \
     backend/stack_health.py \
     backend/compose_import.py \
     backend/traefik.py \
     backend/apply.py \
     backend/generator.py \
     ./

COPY --from=frontend-builder /frontend/dist ./static

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]

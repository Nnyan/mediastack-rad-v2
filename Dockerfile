# ── Stage 1: Build Vue frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install --ignore-scripts

COPY frontend/ ./
RUN npm run build
# dist/ is now at /frontend/dist

# ── Stage 2: Python backend + serve frontend ──────────────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/main.py ./

# Copy built Vue assets so FastAPI's StaticFiles serves them
COPY --from=frontend-builder /frontend/dist ./static

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]

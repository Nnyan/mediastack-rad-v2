FROM python:3.12-slim AS backend

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Frontend static files are copied here during multi-stage build
# (see root Dockerfile)

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/api/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]

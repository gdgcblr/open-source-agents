# Ishikawa RCA web UI. Runs on Cloud Run or any container host.
#   docker build -t ishikawa-rca . && docker run -p 8080:8080 --env-file .env ishikawa-rca
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ishikawa/ ishikawa/
COPY fixtures/ fixtures/
COPY recordings/ recordings/
COPY web/ web/
COPY server.py mcp_server.py ./
RUN mkdir -p runs && chown app runs  # audit trail is the only path the app writes

USER app
EXPOSE 8080
# Cloud Run injects $PORT; bind all interfaces inside the container only.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]

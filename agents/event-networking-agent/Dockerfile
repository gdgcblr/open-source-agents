FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY networking_agent ./networking_agent
COPY config ./config
COPY web ./web

# One process only: event state lives in memory (see Known Limitations in the README).
CMD exec uvicorn networking_agent.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --workers 1

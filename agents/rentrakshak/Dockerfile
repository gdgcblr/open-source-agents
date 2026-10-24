# RentRakshak — production-style image for CLI, tests, and optional UI.
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RENTRAKSHAK_DB_PATH=/data/rentrakshak.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 rentrakshak \
    && useradd --uid 1000 --gid 1000 --create-home rentrakshak

# Dependencies first (better layer cache)
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Application code
COPY rentrakshak ./rentrakshak
COPY adk_agent ./adk_agent
COPY data ./data
COPY tests ./tests
COPY scripts ./scripts
COPY main.py ./

RUN pip install -e ".[dev]"

RUN mkdir -p /data && chown -R rentrakshak:rentrakshak /app /data

USER rentrakshak

# Default: run offline test suite (CI / smoke)
CMD ["pytest", "-q"]

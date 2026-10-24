FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system auditor \
    && useradd --system --gid auditor --home-dir /home/auditor auditor \
    && mkdir -p /workspace \
    && chown auditor:auditor /workspace \
    && git config --system --add safe.directory /workspace

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install .

WORKDIR /workspace
USER auditor

ENTRYPOINT ["pr-security-auditor"]

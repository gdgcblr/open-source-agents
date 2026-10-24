FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    MIGINE_DATA_DIR=/data LITELLM_TELEMETRY=False \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && useradd --uid 10001 --create-home migine \
    && mkdir /data && chown migine:migine /data
USER 10001:10001
VOLUME ["/data"]
ENTRYPOINT ["migine"]
CMD ["--help"]

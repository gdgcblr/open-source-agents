FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home app \
    # /repos is a read-only mount owned by the host user; let git list its files (fsmonitor is disabled in code)
    && git config --system --add safe.directory '*'
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY reviewer ./reviewer
COPY serve_a2a.py ./
RUN chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" HOST=0.0.0.0 PORT=8001 REVIEW_ROOT=/repos
EXPOSE 8001
CMD ["python", "serve_a2a.py"]

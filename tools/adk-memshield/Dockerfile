FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed_cache \
    PYTHONPATH=/app/src

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "google-adk>=2.12.0,<3" \
        "psycopg[binary,pool]>=3.1.0" \
        "fastembed>=0.3.0" \
        "pydantic>=2.6.0" \
        "pytest>=8.0.0" \
        "pytest-asyncio>=0.23.0" \
        "build>=1.0.0" \
        "hatchling>=1.27.0"

# Pre-warm and cache BAAI/bge-small-en-v1.5 (384d) inside the image for zero-latency offline runs
RUN python -c "from fastembed import TextEmbedding; m = TextEmbedding(model_name='BAAI/bge-small-en-v1.5'); list(m.embed(['adk-memshield warmup']))"

COPY . /app
RUN pip install --no-cache-dir --no-deps -e .

CMD ["pytest", "-v"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed_cache

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyPI dependencies including adk-memshield>=0.1.0 and google-adk
RUN pip install --no-cache-dir \
    "adk-memshield>=0.1.0" \
    "google-adk>=1.0.0" \
    "fastapi>=0.115.0" \
    "uvicorn>=0.32.0" \
    "litellm>=1.50.0" \
    "httpx>=0.27.0" \
    "psycopg[binary,pool]>=3.2.0" \
    "pydantic>=2.7.0" \
    "fastembed>=0.4.0" \
    "numpy>=1.26" \
    "pytest>=8.0.0" \
    "pytest-asyncio>=0.24.0"

# Pre-cache FastEmbed ONNX model (BAAI/bge-small-en-v1.5) for zero-latency offline startup
RUN mkdir -p /opt/fastembed_cache && \
    python -c "from fastembed import TextEmbedding; list(TextEmbedding('BAAI/bge-small-en-v1.5').embed(['adk-leak-arena warmup']))"

COPY pyproject.toml README.md LICENSE ./
COPY sql ./sql
COPY src ./src
COPY tests ./tests

RUN pip install --no-cache-dir --no-deps -e .

EXPOSE 8090

CMD ["leak-arena", "serve", "--host", "0.0.0.0", "--port", "8090"]

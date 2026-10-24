# ==============================================================================
# RepoLens — Backend Dockerfile
# Python 3.11 + Git + Trivy + Semgrep + FastAPI + Google ADK
# ==============================================================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies & Trivy security scanner
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify scanner and git installations
RUN git --version && trivy --version

# Copy requirements and install Python dependencies (including Semgrep)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt semgrep && semgrep --version

# Copy application source code
COPY backend/ ./backend/
COPY agent/ ./agent/
COPY db/ ./db/
COPY scripts/ ./scripts/
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

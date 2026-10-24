FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROJECT_DIR=/workspace \
    OUTPUT_DIR=/output

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY readme_drafter/ ./readme_drafter/
COPY tests/ ./tests/

# Run as an unprivileged user; the project being documented is mounted read-only.
RUN useradd --create-home --uid 1000 drafter \
    && mkdir -p /output \
    && chown -R drafter /app /output
USER drafter

EXPOSE 8000
CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8000", "/app/readme_drafter"]

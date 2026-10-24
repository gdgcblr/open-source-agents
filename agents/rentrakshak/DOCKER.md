# RentRakshak — Docker

Run the agent **without installing Python on the host**. The image includes the app, datasets, tests, and ADK dependencies. **No API key** is required for `test` or `cli` services.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/) v2 (`docker compose`)

## Quick start

```bash
cd agents/rentrakshak

# Build image (first time or after code changes)
docker compose build

# Run full offline test suite (32 tests)
docker compose run --rm test

# Run deterministic safety report on suspicious fixture
docker compose run --rm cli

# Seed SQLite demo data into a named volume
docker compose run --rm seed
```

## Plain `docker run` (without Compose)

```bash
docker build -t rentrakshak:local .

# Tests (default CMD)
docker run --rm rentrakshak:local

# Custom safety report
docker run --rm rentrakshak:local \
  python main.py --listing @tests/fixtures/clean_listing.txt

# Persist community DB
docker run --rm -v rentrakshak-data:/data \
  -e RENTRAKSHAK_DB_PATH=/data/rentrakshak.db \
  rentrakshak:local python scripts/seed_demo_data.py
```

## Environment variables

| Variable | Default in image | Purpose |
|----------|------------------|---------|
| `RENTRAKSHAK_DB_PATH` | `/data/rentrakshak.db` | SQLite path (use volume `/data`) |
| `GOOGLE_API_KEY` | unset | Only for `adk run` / Gemini (not used by default CMD) |

Copy `.env.example` for local non-Docker runs. For Compose, set `environment:` on a custom service override.

## Image details

- Base: `python:3.12-slim-bookworm`
- Non-root user: `rentrakshak` (uid 1000)
- Working directory: `/app`
- Default command: `pytest -q`

## Local Gemma (Ollama on host + container)

Ollama usually runs on the **host** (not inside the image). From a container:

```bash
docker compose run --rm \
  -e RENTRAKSHAK_LLM_BACKEND=ollama \
  -e RENTRAKSHAK_OLLAMA_MODEL=gemma3:4b \
  -e OLLAMA_API_BASE=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  cli
```

For interactive ADK with Ollama, install `requirements-ollama.txt` on the host and run `adk web adk_agent` locally (simplest).

## ADK in Docker (optional)

```bash
docker run --rm -it -e GOOGLE_API_KEY=your_key \
  rentrakshak:local adk run adk_agent
```

Interactive; requires TTY (`-it`).

## UI (later)

Streamlit is not the default Docker entrypoint. When you re-enable UI, add a compose service that runs `streamlit run ui/streamlit_app.py` and mount/copy the `ui/` folder.

## Verify after changes

```bash
make docker-smoke
```

Runs `build` → `test` → `cli` in sequence.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Build slow | First build downloads `google-adk` and dependencies; cached on rebuild |
| Permission on volume | Image uses uid 1000; on Linux bind-mounts, match ownership if needed |
| `seed` says DB exists | `docker volume rm rentrakshak_rentrakshak-data` (destructive) |

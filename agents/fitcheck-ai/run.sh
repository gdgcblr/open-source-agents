#!/usr/bin/env bash
# One-command start for FitCheck AI — works from any folder.
#   bash agents/fitcheck-ai/run.sh
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  [ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found — install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1
fi

[ -d .venv ] || uv venv --python 3.12
. .venv/bin/activate
uv pip install -q -r requirements.txt

if [ ! -f .env ]; then
  echo "⚠  No .env file — copy .env.example to .env and add your GOOGLE_API_KEY."; exit 1
fi

# Free port 8000 if an old FitCheck server is still holding it
PORT="${PORT:-8000}"
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT is busy — stopping the old server…"
  lsof -ti tcp:"$PORT" | xargs kill 2>/dev/null || true
  sleep 1
fi

echo "Starting FitCheck AI → http://127.0.0.1:$PORT"
exec python server.py

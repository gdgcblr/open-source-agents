#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  PYTHON_BIN=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
  if [[ -z "$PYTHON_BIN" ]]; then
    echo "Python 3.11+ is required. Install Python and rerun this command." >&2
    exit 1
  fi
  "$PYTHON_BIN" -m venv "$PROJECT_ROOT/.venv"
  echo "Created .venv. The agent uses Python standard-library modules only."
fi

if ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "The existing .venv uses Python older than 3.11. Remove .venv and rerun with Python 3.11+." >&2
  exit 1
fi

if [[ " ${*:-} " == *" --allow-execution "* ]]; then
  DOCKER_BIN="${REPRO_CAPSULE_DOCKER_BIN:-$(command -v docker || true)}"
  if [[ -z "$DOCKER_BIN" && -x "$HOME/.docker/bin/docker" ]]; then
    DOCKER_BIN="$HOME/.docker/bin/docker"
  fi
  if [[ -z "$DOCKER_BIN" ]]; then
    echo "Docker Engine is required for test execution. Install and start Docker, then rerun." >&2
    exit 1
  fi
  export REPRO_CAPSULE_DOCKER_BIN="$DOCKER_BIN"
  "$DOCKER_BIN" info >/dev/null 2>&1 || {
    echo "Docker is installed but not running. Start Docker and retry." >&2
    exit 1
  }
  if ! "$DOCKER_BIN" image inspect python:3.12-slim >/dev/null 2>&1; then
    echo "Pulling required test image python:3.12-slim..."
    "$DOCKER_BIN" pull python:3.12-slim
  fi
fi

ENV_FILE="$PROJECT_ROOT/.env"
DOTENV_HAS_KEY=0
if [[ -f "$ENV_FILE" ]] && grep -qE '^[[:space:]]*GEMINI_API_KEY[[:space:]]*=[^[:space:]]+' "$ENV_FILE"; then
  DOTENV_HAS_KEY=1
fi

if [[ "${1:-}" == "investigate" && -z "${GEMINI_API_KEY:-}" && "$DOTENV_HAS_KEY" -eq 0 ]]; then
  read -r -s -p "Gemini API key (input hidden; used for this run only): " GEMINI_API_KEY
  echo
  export GEMINI_API_KEY
  trap 'unset GEMINI_API_KEY' EXIT
fi

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV_PYTHON" -m repro_capsule.cli "$@"

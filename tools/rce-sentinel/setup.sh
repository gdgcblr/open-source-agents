#!/usr/bin/env bash
# One-step setup for rce-sentinel.
#   ./setup.sh            install the tool (Python venv + ESLint backend)
#   ./setup.sh --models   also start Ollama on :11436 and pull qwen2.5:3b + gemma4:31b-cloud
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
"$PY" - <<'PYCHECK' || { echo "Python 3.11+ is required (set PYTHON=/path/to/python3.12)"; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PYCHECK

echo "[1/3] Python environment"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e '.[dev]'

echo "[2/3] ESLint backend for JS/TS (optional)"
if command -v node >/dev/null 2>&1 && node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>20||(a===20&&b>=19)?0:1)'; then
  (cd linters/eslint && npm ci --ignore-scripts --no-audit --no-fund --silent)
else
  echo "      Node 20.19+ not found: JS/TS will use the regex fallback rules"
fi

echo "[3/3] Models (optional)"
if [ "${1:-}" = "--models" ]; then
  command -v ollama >/dev/null 2>&1 || { echo "      ollama not installed: https://ollama.com"; exit 1; }
  export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11436}"
  if ! curl -s -m 1 "http://$OLLAMA_HOST/api/version" >/dev/null; then
    echo "      starting ollama on $OLLAMA_HOST"
    nohup ollama serve >/tmp/rce-sentinel-ollama.log 2>&1 &
    for _ in $(seq 1 40); do curl -s -m 1 "http://$OLLAMA_HOST/api/version" >/dev/null && break; sleep 0.25; done
  fi
  ollama pull qwen2.5:3b
  ollama pull gemma4:31b-cloud
  echo "      for the cloud model, sign in once:  OLLAMA_HOST=$OLLAMA_HOST ollama signin"
else
  echo "      skipped (run ./setup.sh --models to pull qwen2.5:3b and gemma4:31b-cloud)"
fi

cat <<'DONE'

Installed. Next:
  source .venv/bin/activate
  rce-sentinel trace --real-only --file demo/prompts/1_flask_injection.py   # works with no models
  export OLLAMA_BASE_URL=http://127.0.0.1:11436/v1 && rce-sentinel doctor  # check your models
DONE

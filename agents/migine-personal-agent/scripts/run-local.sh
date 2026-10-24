#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
if [ "${TERM_PROGRAM:-}" = vscode ]; then
  echo 'Calendar access may be blocked in VS Code. Use the macOS Terminal app if access fails.' >&2
fi
if [ ! -f .env ]; then
  echo 'Run sh scripts/setup-local.sh first.' >&2
  exit 1
fi
MIGINE_MAC_HELPER="$(uv run --frozen python scripts/setup_local.py --helper-path)"
export MIGINE_MAC_HELPER
echo 'Open http://127.0.0.1:8000 and select migine_web.'
echo 'Keep this terminal open. Press Ctrl+C to stop.'
exec uv run --frozen adk web examples/web --host 127.0.0.1 --port 8000 --max_llm_calls 8

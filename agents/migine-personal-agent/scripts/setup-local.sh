#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
if [ "$(uname -s)" != Darwin ]; then
  echo 'Local setup requires macOS.' >&2
  exit 1
fi
for dependency in uv ollama xcrun; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    echo "Install $dependency before running local setup." >&2
    exit 1
  fi
done
if [ ! -f .env ]; then
  cp .env.example .env
fi
uv sync --frozen
uv run --frozen python scripts/setup_local.py

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
exec uvicorn rentrakshak.api.server:app --host 127.0.0.1 --port 8080 --reload

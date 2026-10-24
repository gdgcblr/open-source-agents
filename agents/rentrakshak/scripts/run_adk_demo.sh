#!/usr/bin/env bash
# Start Google ADK Web UI for RentRakshak (agentic demo — LLM picks tools).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

# Local Gemma (default for demo without GOOGLE_API_KEY)
export RENTRAKSHAK_LLM_BACKEND="${RENTRAKSHAK_LLM_BACKEND:-ollama}"
export RENTRAKSHAK_OLLAMA_MODEL="${RENTRAKSHAK_OLLAMA_MODEL:-gemma3:4b}"

if [[ "${RENTRAKSHAK_LLM_BACKEND}" == "ollama" ]]; then
  python scripts/check_ollama.py || {
    echo "Fix Ollama first: open Ollama app or run 'ollama serve', then: ollama pull gemma3:4b"
    exit 1
  }
fi

PORT="${RENTRAKSHAK_ADK_PORT:-8000}"
echo ""
echo "  RentRakshak ADK agent → http://127.0.0.1:${PORT}/dev-ui/"
echo "  (Product HTML demo stays on http://127.0.0.1:8080 if you run run_web_demo.sh)"
echo ""

exec adk web adk_agent --host 127.0.0.1 --port "$PORT"

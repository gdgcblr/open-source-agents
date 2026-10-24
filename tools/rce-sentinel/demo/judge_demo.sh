#!/usr/bin/env bash
# Live demo for judges: feed prompts (code snippets) to rce-sentinel and watch which
# security tools fire and which model handles each step.
#
#   ./demo/judge_demo.sh            # models that are up answer for real; the rest are mocked
#
# Output includes each model's exact prompt and raw reply (trace --show-io).
# Needs for the real run: apfel (Apple Intelligence on), ollama with qwen2.5:3b and
# gemma4:31b-cloud (`OLLAMA_HOST=127.0.0.1:11436 ollama signin` once for the cloud model).
# Everything is offline except calls to those models; the demo state lives in a temp dir.
set -uo pipefail

TOOL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${RCE_SENTINEL_BIN:-$(command -v rce-sentinel || echo "$TOOL_DIR/.venv/bin/rce-sentinel")}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rce-sentinel-judge.XXXXXX")"
LOG_PREFIX="$WORK/srv"
export RCE_SENTINEL_OFFLINE=1
export RCE_SENTINEL_KEY_FILE="$WORK/signing.key"
export RCE_SENTINEL_PROVIDER="${RCE_SENTINEL_PROVIDER:-hybrid}"
STATE="$WORK/state"
# shellcheck source=demo/_models.sh
. "$TOOL_DIR/demo/_models.sh"
trap models_cleanup EXIT
step() { printf '\n\033[1m=== %s\033[0m\n' "$*"; }
trace() { "$BIN" trace --state "$STATE" --osv-seed "$TOOL_DIR/demo/osv_seed.json" "$@"; }

step "0. Models (real calls, not pings)"
start_apfel || true
start_ollama || true
"$BIN" --repo "$WORK" doctor || echo "(a FAIL above means that model is mocked in this demo)"

step "1. Prompt: Flask handler with a prompt-injection comment (cold: models switch)"
trace --show-io --file "$TOOL_DIR/demo/prompts/1_flask_injection.py"

step "2. Same prompt again: served from the signed cache, zero model calls"
trace --file "$TOOL_DIR/demo/prompts/1_flask_injection.py" | sed -n '/\[4\]/,/\[6\]/p;/\[7\]/,$p'

step "3. Constant command: the pre-router needs no model at all"
trace --file "$TOOL_DIR/demo/prompts/2_constant_sink.py" | sed -n '/\[2\]/,/\[4\]/p;/\[7\]/,$p'

step "4. JavaScript prompt: ESLint plugin + AST taint"
trace --file "$TOOL_DIR/demo/prompts/3_express.js"

step "5. Dependency prompt: PyYAML 5.3 plus a real call to yaml.load (OSV + reachability)"
trace --file "$TOOL_DIR/demo/prompts/4_yaml_dependency.py" --req "PyYAML==5.3" \
  | sed -n '/\[3\]/,/\[4\]/p;/\[7\]/,$p'

step "6. Token quota: a 5-endpoint service, apfel capped at 1,500 tokens for this run"
echo "(apfel judges the first findings, hits its quota, and later calls move to other models)"
RCE_SENTINEL_QUOTA="apple-foundationmodel=1500" \
  trace --show-io --file "$TOOL_DIR/demo/prompts/5_multi_endpoint_service.py"

step "7. Memory shield: an attacker flips every cached verdict to safe in SQLite"
DB="$STATE/workspace/.rce-sentinel/sentinel.db"
echo "signed cached verdicts: $(sqlite3 "$DB" 'SELECT COUNT(*) FROM result_cache')"
sqlite3 "$DB" "UPDATE result_cache SET verdict_json = replace(verdict_json, '\"vulnerable\"', '\"safe\"')"
echo "rescanning prompt 1 after tampering:"
trace --file "$TOOL_DIR/demo/prompts/1_flask_injection.py" | sed -n '/\[4\]/,/\[5\]/p;/\[6\]/,$p'

step "8. A2A audit log"
sqlite3 -header -column "$DB" "SELECT kind, COUNT(*) AS msgs FROM a2a_log GROUP BY kind ORDER BY kind"
echo
echo "Demo state kept at $WORK (delete when done)."

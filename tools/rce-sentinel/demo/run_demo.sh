#!/usr/bin/env bash
# End-to-end demo in a throwaway git repo:
#   1. pre-commit blocks os.system(user_input)
#   2. a lockfile-only commit makes zero LLM calls; post-commit rescans the tree
#   3. a repeat scan is served from the verdict cache
#   4. cost report vs the all-strongest-model baseline
#   5. a simulated CISA KEV entry produces a draft mitigation (never applied or pushed)
#
# Models: Apple's on-device Foundation Model via apfel (brew install apfel) and local
# qwen2.5:3b via Ollama (ollama pull qwen2.5:3b). The demo starts `apfel --serve` on :11435
# and, if needed, `ollama serve` on :11436 (11434 is often taken by apfel's launch agent).
# Hybrid mode: whatever is up answers for real; the rest falls back to the labelled mock.
# The Ollama cloud model needs `OLLAMA_HOST=127.0.0.1:11436 ollama signin`; without it the
# router reports an authentication fallback and moves on.
# Override with RCE_SENTINEL_PROVIDER=mock|auto|hybrid|off. OSV/intel stay offline.
set -uo pipefail

TOOL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${RCE_SENTINEL_BIN:-$(command -v rce-sentinel || echo "$TOOL_DIR/.venv/bin/rce-sentinel")}"
export RCE_SENTINEL_OFFLINE="${RCE_SENTINEL_OFFLINE:-1}"
export RCE_SENTINEL_CAVEMAN_PROBE="${RCE_SENTINEL_CAVEMAN_PROBE:-1}"
unset RCE_SENTINEL_HOME

DEMO="$(mktemp -d "${TMPDIR:-/tmp}/rce-sentinel-demo.XXXXXX")"
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

LOG_PREFIX="$DEMO"
export RCE_SENTINEL_KEY_FILE="$DEMO.key"   # per-machine signing key, kept outside the repo
# shellcheck source=demo/_models.sh
. "$TOOL_DIR/demo/_models.sh"
trap models_cleanup EXIT

step "Models"
if [ -z "${RCE_SENTINEL_PROVIDER:-}" ]; then
  real=0
  start_apfel && real=1
  start_ollama && real=1
  if [ "$real" = 1 ]; then
    export RCE_SENTINEL_PROVIDER=hybrid
    echo "hybrid: models that are up answer for real; the rest use the labelled mock"
  else
    export RCE_SENTINEL_PROVIDER=mock
    echo "no local model is up: mock provider for every tier"
  fi
else
  if [ "$RCE_SENTINEL_PROVIDER" != mock ]; then start_apfel || true; start_ollama || true; fi
  echo "provider mode: $RCE_SENTINEL_PROVIDER"
fi

step "Setting up a throwaway repo at $DEMO"
cp -R "$TOOL_DIR/tests/fixtures/vuln_repo/." "$DEMO/"
cd "$DEMO" || exit 1
git init -q -b task/rce-sentinel-demo
git config user.email demo@example.com
git config user.name "rce-sentinel demo"
git add . && git -c core.hooksPath=/dev/null commit -qm "fixture app (intentionally vulnerable)"
"$BIN" install-hooks
"$BIN" osv-import "$TOOL_DIR/tests/fixtures/osv_seed.json"

step "1. Commit os.system(user_input): pre-commit should block"
cat > svc.py <<'EOF'
import os


def handler():
    user_input = input("host: ")
    os.system("ping -c 1 " + user_input)
EOF
git add svc.py
if git commit -qm "add ping handler"; then
  echo "UNEXPECTED: commit went through"
else
  echo "-> commit blocked (exit $?). Escape hatch: git commit --no-verify"
fi
git reset -q svc.py

step "2. Lockfile-only commit: zero LLM calls, then post-commit full rescan"
echo "Jinja2==3.1.4" >> requirements.txt
git add requirements.txt
git commit -qm "add jinja2" && echo "-> commit allowed"
sqlite3 .rce-sentinel/sentinel.db \
  "SELECT 'pre-commit run used ' || COUNT(c.id) || ' LLM call(s)' FROM runs r
   LEFT JOIN llm_calls c ON c.run_id = r.run_id WHERE r.mode='pre-commit'
   GROUP BY r.run_id ORDER BY r.started DESC LIMIT 1" 2>/dev/null || true

step "3. Repeat full scan of unchanged code: served from cache"
"$BIN" scan 2>&1 | head -1

step "4. Cost report"
"$BIN" cost-report

step "5. Simulated KEV entry for PyYAML (plus an unconfirmed social rumour)"
HEAD_BEFORE="$(git rev-parse HEAD)"
"$BIN" watch --simulate "$TOOL_DIR/demo/simulated_kev.json"
PROPOSAL="$(ls -d .rce-sentinel/proposals/CVE-2020-14343-* | head -1)"
echo "--- $PROPOSAL/mitigation.patch"
cat "$PROPOSAL/mitigation.patch"
echo "--- $PROPOSAL/ADVISORY.md (head)"
head -8 "$PROPOSAL/ADVISORY.md"
echo "--- git state after the intel run"
[ "$(git rev-parse HEAD)" = "$HEAD_BEFORE" ] && echo "HEAD unchanged: no commit, no push"
git status --short --untracked-files=no | sed 's/^/  /'
step "6. Memory shield: someone tampers with the stored verdicts"
DB=.rce-sentinel/sentinel.db
echo "before: $(sqlite3 "$DB" "SELECT COUNT(*) FROM result_cache") signed cached verdicts"
sqlite3 "$DB" "UPDATE result_cache SET verdict_json = replace(verdict_json, '\"vulnerable\"', '\"safe\"')"
echo "attacker flipped every cached verdict to \"safe\" directly in SQLite, then we rescan:"
"$BIN" scan 2>&1 | grep -E "rce-sentinel full|degraded|py-os-system" | head -4

step "7. A2A audit: signed, role-checked, hash-chained agent messages"
sqlite3 -header -column "$DB" \
  "SELECT kind, COUNT(*) AS msgs, MIN(trust) AS min_trust, MAX(trust) AS max_trust
   FROM a2a_log GROUP BY kind ORDER BY kind"
echo "(payloads are never stored, only their hashes and the signature chain)"
echo
echo "Demo repo kept at $DEMO (delete it when done)."

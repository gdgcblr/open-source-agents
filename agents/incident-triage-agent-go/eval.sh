#!/usr/bin/env bash
# Scores the agent against the lab's known faults. For each scenario: reset
# the lab, wait for alerts to clear, inject the fault, wait for an alert to
# fire, run one triage, and check the "Most likely root cause" section names
# the right service and cause (and does not blame the known noise).
#   ./eval.sh                 # all scenarios
#   ./eval.sh latency pool    # a subset
set -uo pipefail
cd "$(dirname "$0")"

PROM=${PROMETHEUS_URL:-http://localhost:9090}
BIN=${TRIAGE_BIN:-./incident-triage-agent}
mkdir -p runs

# scenario | service that must be named | cause keywords (regex)
# Order matters: reset rolls checkout back to v1.3.0, which later scenarios see
# as a deploy, so the deploy scenario runs after the pool one.
SCENARIOS=(
  "latency|payments|latenc|slow"
  "pool|checkout|pool|connection"
  "bad-deploy|checkout|v1\.4\.0|deploy"
  "leak|checkout|memory|leak|oom"
)

firing() { curl -s "$PROM/api/v1/alerts" | grep -c '"state":"firing"'; }
wait_for() { # wait_for <seconds> <condition command...>
  local deadline=$((SECONDS + $1)); shift
  until "$@"; do (( SECONDS > deadline )) && return 1; sleep 5; done
}
no_alerts() { [ "$(firing)" -eq 0 ]; }
some_alert() { [ "$(firing)" -gt 0 ]; }

go build -o "$BIN" . || exit 1
pass=0; total=0
for row in "${SCENARIOS[@]}"; do
  name=${row%%|*}; rest=${row#*|}; service=${rest%%|*}; cause=${rest#*|}
  [ $# -gt 0 ] && [[ " $* " != *" $name "* ]] && continue
  total=$((total + 1))
  echo "=== $name: expect $service + /$cause/"
  ./lab/chaos.sh reset >/dev/null
  wait_for 240 no_alerts || echo "  (alerts still firing after reset; continuing)"
  sleep 30   # let a clean baseline window accumulate
  ./lab/chaos.sh "$name" >/dev/null
  if ! wait_for 240 some_alert; then echo "  FAIL: no alert fired"; continue; fi

  report="runs/$name.md"
  "$BIN" triage -trace "runs/$name.json" < /dev/null > "$report" 2> "runs/$name.log"
  rc=$(awk '/^## Most likely root cause/{f=1; next} /^## /{f=0} f' "$report")
  if echo "$rc" | grep -qi "$service" && echo "$rc" | grep -qiE "$cause" &&
     ! echo "$rc" | grep -qiE 'exchange|fx[-_ ]'; then
    echo "  PASS  $(echo "$rc" | head -1)"; pass=$((pass + 1))
  else
    echo "  FAIL  root cause was: $(echo "$rc" | tr '\n' ' ' | cut -c1-200)"
  fi
  grep '^■' "runs/$name.log" | sed 's/^/  /'
done
./lab/chaos.sh reset >/dev/null
echo "=== score: $pass/$total"

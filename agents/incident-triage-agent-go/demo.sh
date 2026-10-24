#!/usr/bin/env bash
# One-command live demo: reset the lab, break it, wait for the alert, triage.
#   ./demo.sh                # latency fault (default)
#   ./demo.sh pool           # or: bad-deploy | leak
# Uses a local model unless MODEL_PROVIDER is set (MODEL_PROVIDER=gemini for Gemini).
set -uo pipefail
cd "$(dirname "$0")"

SCENARIO=${1:-latency}
PROM=${PROMETHEUS_URL:-http://localhost:9090}
export MODEL_PROVIDER=${MODEL_PROVIDER:-openai}
[ "$MODEL_PROVIDER" = openai ] && export MODEL_NAME=${MODEL_NAME:-qwen3:4b-instruct}

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
firing() { curl -s "$PROM/api/v1/alerts" | grep -c '"state":"firing"'; }

mkdir -p runs
go build -o runs/.demo-agent . || exit 1

bold "1/4  Resetting the lab to a healthy state"
./lab/chaos.sh reset >/dev/null
for _ in $(seq 1 40); do [ "$(firing)" -eq 0 ] && break; printf '.'; sleep 3; done
echo " healthy"

bold "2/4  Breaking something (the agent is not told what)"
./lab/chaos.sh "$SCENARIO" >/dev/null && echo "fault '$SCENARIO' injected at $(date +%T)"

bold "3/4  Waiting for Prometheus to page (1m rate window + 30s 'for')"
start=$SECONDS
until [ "$(firing)" -gt 0 ]; do
  printf '\r  %3ss  ' $((SECONDS - start)); ./lab/chaos.sh alerts 2>/dev/null | tr '\n' ' '; sleep 3
done
echo; ./lab/chaos.sh alerts

bold "4/4  Agent investigating ($MODEL_PROVIDER/${MODEL_NAME:-default})"
runs/.demo-agent triage -trace "runs/demo-$SCENARIO.json" < /dev/null | tee "runs/demo-$SCENARIO.md"

case "$SCENARIO" in
  latency)    truth="payments is slow (+1.5s); checkout only suffers from calling it" ;;
  pool)       truth="checkout DB connection pool exhausted (503s); the fx-refresh errors are old noise" ;;
  bad-deploy) truth="checkout v1.4.0 deploy throws 500s in applyCoupon" ;;
  leak)       truth="checkout leaks memory and gets OOM-killed" ;;
esac
bold "Ground truth: $truth"
echo "Audit trail: runs/demo-$SCENARIO.json · reset with ./lab/chaos.sh reset"

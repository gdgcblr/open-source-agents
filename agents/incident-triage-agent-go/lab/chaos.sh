#!/usr/bin/env bash
# Inject a known fault into the lab. Each scenario has one true root cause.
#   ./chaos.sh latency | bad-deploy | pool | leak | reset | status | alerts
set -euo pipefail

CHECKOUT=${CHECKOUT_URL:-http://localhost:8080}
PAYMENTS=${PAYMENTS_URL:-http://localhost:8081}

post() { curl -sf -X POST "$1/chaos" -d "$2"; echo; }

case "${1:-status}" in
  latency)     # root cause: payments is slow; checkout is only the victim
    post "$PAYMENTS" '{"latency_ms": 1500}' ;;
  bad-deploy)  # root cause: checkout v1.4.0 introduced a crash in coupon code
    post "$CHECKOUT" '{"version": "v1.4.0", "error_rate": 0.3, "error_code": 500,
      "error_msg": "panic recovered: nil pointer dereference in applyCoupon"}' ;;
  pool)        # root cause: checkout DB pool exhausted (fx-refresh noise is a red herring)
    post "$CHECKOUT" '{"error_rate": 0.25, "error_code": 503,
      "error_msg": "acquire db connection: pool exhausted (max=10)"}' ;;
  leak)        # root cause: checkout leaks memory and is OOM-killed in a loop
    post "$CHECKOUT" '{"leak_kb_per_req": 48}' ;;
  reset)
    curl -sf -X POST "$CHECKOUT/chaos/reset"; echo
    curl -sf -X POST "$PAYMENTS/chaos/reset"; echo
    post "$CHECKOUT" '{"version": "v1.3.0"}' >/dev/null ;;
  status)
    curl -sf "$CHECKOUT/chaos"; curl -sf "$PAYMENTS/chaos" ;;
  alerts)      # alerts take ~90s to fire: 1m rate window + 30s "for"
    curl -sf "${PROMETHEUS_URL:-http://localhost:9090}/api/v1/alerts" |
      grep -oE '"alertname":"[^"]+"|"service":"[^"]+"|"state":"[^"]+"' |
      sed -E 's/"([a-z]+)":"([^"]+)"/\2/' | paste - - - | column -t
    ;;
  *) echo "usage: $0 latency|bad-deploy|pool|leak|reset|status|alerts" >&2; exit 1 ;;
esac

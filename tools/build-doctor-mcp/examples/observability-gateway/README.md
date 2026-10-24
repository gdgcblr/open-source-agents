# Observability Gateway Adapter

BuildDoctor intentionally does not own vendor credentials or poll monitoring APIs. Put provider-specific webhook handling in a small authenticated gateway, then pass only the normalized alert contract to the MCP server.

## Gateway Responsibilities

1. Verify the provider's native webhook signature using the provider's official SDK or documentation.
2. Reject replayed, expired, malformed, or duplicate events.
3. Map vendor fields into [`../observability-alert.json`](../observability-alert.json).
4. Remove secrets, raw headers, private payloads, and unnecessary dimensions.
5. Compute an HMAC-SHA256 signature using `BUILD_DOCTOR_WEBHOOK_SECRET`.
6. Call `verify_alert_signature` before calling `analyze_alert`.

## Provider Adapters

The server includes small field-alias adapters for `new-relic` and `cubeapm` in `src/build_doctor_mcp/adapters.py`. They normalize service, metric, value, threshold, and correlation identifiers. They do not verify provider signatures because signature formats and credential handling belong in the gateway.

The same extension point can support Prometheus Alertmanager, OpenTelemetry collectors, Grafana, Datadog, PagerDuty, or an internal alerting system without changing the diagnostic engine.

## Safety Contract

- The gateway owns provider secrets and signature verification.
- BuildDoctor owns normalized evidence scoring and next-evidence guidance.
- BuildDoctor does not acknowledge, suppress, mutate, rollback, or remediate production alerts.
- A threshold breach is an incident signal, not a root-cause conclusion.

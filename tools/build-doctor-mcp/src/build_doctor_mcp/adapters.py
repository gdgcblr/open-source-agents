"""Provider-specific alert normalization hooks for an authenticated gateway."""

from __future__ import annotations

from typing import Any


_PROVIDER_ALIASES = {
    "new-relic": {
        "service": {"entityName", "applicationName", "serviceName"},
        "metric": {"conditionName", "policyName", "metricName"},
        "value": {"currentValue", "criticalValue", "value"},
        "threshold": {"criticalThreshold", "threshold", "thresholdValue"},
        "correlation_id": {"incidentId", "issueId", "runbookUrl"},
    },
    "cubeapm": {
        "service": {"serviceName", "appName", "application"},
        "metric": {"metricName", "alertName", "signalName"},
        "value": {"currentValue", "observedValue", "value"},
        "threshold": {"thresholdValue", "threshold", "limit"},
        "correlation_id": {"alertId", "incidentId", "traceId"},
    },
}


def _find(payload: Any, names: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in names and isinstance(value, (str, int, float, bool)):
                return value
        for value in payload.values():
            found = _find(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find(value, names)
            if found is not None:
                return found
    return None


def _event_type(metric: str) -> str:
    value = metric.lower()
    if any(term in value for term in ("latency", "duration", "response_time")):
        return "latency"
    if any(term in value for term in ("error_rate", "error rate", "failure_rate")):
        return "error_rate"
    if any(term in value for term in ("availability", "uptime", "health")):
        return "availability"
    if any(term in value for term in ("cpu", "memory", "saturation", "utilization")):
        return "saturation"
    if any(term in value for term in ("certificate", "tls", "expiry")):
        return "certificate"
    if any(term in value for term in ("queue", "lag", "backlog")):
        return "queue_lag"
    return "unknown"


def normalize_provider_alert(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Map known provider field aliases into BuildDoctor's provider-neutral alert contract."""
    key = provider.lower().strip().replace("_", "-")
    aliases = _PROVIDER_ALIASES.get(key, {})
    metric = _find(payload, aliases.get("metric", set())) or _find(payload, {"metric", "metric_name", "signal", "policy_name", "condition_name"}) or "unknown"
    return {
        "provider": provider or "unknown",
        "event_type": _find(payload, {"event_type", "event", "type", "alert_type", "condition_type"}) or _event_type(str(metric)),
        "service": _find(payload, aliases.get("service", set())) or _find(payload, {"service", "service_name", "entity", "application", "app_name"}),
        "environment": _find(payload, {"environment", "env", "stage"}),
        "metric": metric,
        "value": _find(payload, aliases.get("value", set())) or _find(payload, {"value", "observed_value", "current_value", "actual"}),
        "threshold": _find(payload, aliases.get("threshold", set())) or _find(payload, {"threshold", "threshold_value", "critical_threshold", "limit"}),
        "unit": _find(payload, {"unit", "units"}),
        "condition": _find(payload, {"condition", "operator", "comparison"}) or "above",
        "timestamp": _find(payload, {"timestamp", "occurred_at", "opened_at", "created_at"}),
        "correlation_id": _find(payload, aliases.get("correlation_id", set())) or _find(payload, {"correlation_id", "trace_id", "incident_id", "alert_id"}),
    }

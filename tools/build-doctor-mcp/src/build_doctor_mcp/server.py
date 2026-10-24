"""Read-only BuildDoctor MCP server with deterministic evidence scoring."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeElementTree
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("build-doctor")
SCHEMA_VERSION = "1.1"
_MANIFESTS = (
    "pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml",
    "requirements.txt", "go.mod", "Cargo.toml", "composer.json", "mix.exs",
)
_MAX_FILE_BYTES = min(max(int(os.getenv("BUILD_DOCTOR_MAX_FILE_BYTES", "200000")), 1), 1000000)
_MAX_LOG_CHARS = min(max(int(os.getenv("BUILD_DOCTOR_MAX_LOG_CHARS", "200000")), 1), 1000000)
_MAX_REPORTS = min(max(int(os.getenv("BUILD_DOCTOR_MAX_REPORTS", "20")), 1), 100)
_SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r'''(?i)(["']?(?:api[_-]?key|token|password|secret|client_secret)["']?\s*[:=]\s*["']?)[^"'\s,;}]+'''), r"\1[REDACTED]"),
    (re.compile(r"(?i)(-----BEGIN [A-Z ]+ PRIVATE KEY-----).*?(-----END [A-Z ]+ PRIVATE KEY-----)", re.S), r"\1[REDACTED]\2"),
)

_RULES: tuple[dict[str, Any], ...] = (
    {
        "failure_type": "compilation",
        "signal_id": "compiler-error",
        "pattern": re.compile(r"compilation error|cannot find symbol|syntax error|type error|mismatched types|error\[e\d+\]|error\s+ts\d+|failed to compile", re.I),
        "weight": 4,
        "cause": "A source or compiler configuration issue is likely.",
        "remediation": "Inspect the first compiler error and its source location.",
        "missing": "The affected source file and compiler command are not present.",
    },
    {
        "failure_type": "compilation",
        "signal_id": "source-location",
        "pattern": re.compile(r"\b[\w./-]+\.(?:java|kt|py|js|jsx|ts|tsx|go|rs|rb|cs):\d+(?::\d+)?\b", re.I),
        "weight": 2,
        "cause": "The output identifies a source location that can anchor investigation.",
        "remediation": "Open the reported source location and compare the expected symbol or type.",
        "missing": "The source location does not prove the underlying cause by itself.",
    },
    {
        "failure_type": "dependency-resolution",
        "signal_id": "dependency-resolution-error",
        "pattern": re.compile(r"could not resolve (?:all )?files|could not resolve dependencies|module not found|modulenotfounderror|no module named|no matching distribution|failed to fetch|package .* not found", re.I),
        "weight": 4,
        "cause": "A dependency name, version, lockfile, registry, or access issue may be blocking resolution.",
        "remediation": "Inspect dependency names, versions, lockfiles, and configured registries.",
        "missing": "The dependency manifest, lockfile, and registry response are not present.",
    },
    {
        "failure_type": "dependency-resolution",
        "signal_id": "registry-or-lockfile-context",
        "pattern": re.compile(r"\b(lock[- ]?file|registry|repository|npm|pypi|maven central|crates\.io|go module)\b", re.I),
        "weight": 1,
        "cause": "The output contains package-registry or lockfile context.",
        "remediation": "Compare the configured registry with the dependency source and lockfile.",
        "missing": "The complete dependency configuration is not present.",
    },
    {
        "failure_type": "test-failure",
        "signal_id": "test-summary",
        "pattern": re.compile(r"tests run:.*(failures|errors): [1-9]|there are test failures|tests? failed", re.I),
        "weight": 4,
        "cause": "At least one test failed, but this signal does not establish the underlying cause.",
        "remediation": "Isolate the failing test and compare expected versus actual values.",
        "missing": "The failing test name, stack trace, and expected/actual values are incomplete.",
    },
    {
        "failure_type": "test-failure",
        "signal_id": "assertion-mismatch",
        "pattern": re.compile(r"assertionerror|expected .* but was", re.I),
        "weight": 2,
        "cause": "An assertion mismatch is visible in the supplied output.",
        "remediation": "Inspect the assertion, fixture, and environment-dependent inputs.",
        "missing": "The fixture and complete assertion context are not present.",
    },
    {
        "failure_type": "runtime-or-api",
        "signal_id": "http-status-or-transport",
        "pattern": re.compile(r"(?:http|status|response)\D*(?:401|403|404|408|429|5\d\d)|timeout|connection refused", re.I),
        "weight": 4,
        "cause": "A runtime or API transport failure is observable, but request and service context are needed to separate causes.",
        "remediation": "Inspect method, response status, timeout, correlation ID, and service logs.",
        "missing": "The sanitized request, response body, service logs, and environment are incomplete.",
    },
    {
        "failure_type": "runtime-or-api",
        "signal_id": "exception-or-traceback",
        "pattern": re.compile(r"traceback|\bexception\b|\bpanic:\b|\bfatal error\b", re.I),
        "weight": 2,
        "cause": "The output contains an exception or runtime termination signal.",
        "remediation": "Inspect the first causal stack-trace frame and the inputs immediately before it.",
        "missing": "The complete stack trace and runtime inputs are incomplete.",
    },
    {
        "failure_type": "configuration",
        "signal_id": "configuration-missing-or-invalid",
        "pattern": re.compile(r"missing configuration|invalid configuration|environment variable .* (?:not set|missing)|keyerror|config(?:uration)?error", re.I),
        "weight": 4,
        "cause": "A required configuration value is missing or invalid.",
        "remediation": "Compare the required configuration with the sanitized environment template and validate formats without exposing secrets.",
        "missing": "The required variable name, expected format, and sanitized runtime configuration are incomplete.",
    },
    {
        "failure_type": "permissions-or-access",
        "signal_id": "permission-denied",
        "pattern": re.compile(r"permission denied|access denied|eacces|operation not permitted|forbidden", re.I),
        "weight": 4,
        "cause": "The process or identity lacks access to a requested file, resource, or service.",
        "remediation": "Identify the exact resource and effective identity, then review the minimum required permission without disabling security controls.",
        "missing": "The resource path, effective identity, and policy decision are not present.",
    },
    {
        "failure_type": "network-or-tls",
        "signal_id": "network-resolution-or-tls",
        "pattern": re.compile(r"dns|name resolution|network unreachable|connection reset|ssl(?:error| certificate)|certificate verify failed|tls handshake", re.I),
        "weight": 4,
        "cause": "A network, DNS, TLS, or certificate validation problem may be blocking communication.",
        "remediation": "Check the sanitized endpoint, DNS result, certificate chain, proxy, and connectivity from the same runtime environment.",
        "missing": "The endpoint, network environment, certificate details, and correlation context are incomplete.",
    },
    {
        "failure_type": "resource-exhaustion",
        "signal_id": "resource-limit",
        "pattern": re.compile(r"out of memory|oomkilled|disk full|no space left|too many open files|quota exceeded|resource exhausted", re.I),
        "weight": 4,
        "cause": "The process or environment reached a memory, storage, file, or service quota limit.",
        "remediation": "Measure the affected resource and usage trend, then reduce scope or adjust an approved limit after review.",
        "missing": "The resource limit, current usage, process size, and host/container context are incomplete.",
    },
    {
        "failure_type": "data-or-schema",
        "signal_id": "data-validation-or-migration",
        "pattern": re.compile(r"json(?:decode|parse)|schema validation|validationerror|deserialization|migration failed|invalid (?:input|payload|format)", re.I),
        "weight": 4,
        "cause": "The input data, serialized shape, schema, or migration state is incompatible with the consumer.",
        "remediation": "Compare the sanitized payload and schema versions, then validate the smallest failing fixture or migration step.",
        "missing": "The schema version, sanitized payload, migration state, and expected shape are incomplete.",
    },
    {
        "failure_type": "container-or-ci",
        "signal_id": "container-or-runner-failure",
        "pattern": re.compile(r"docker build failed|image pull failed|container exited|runner lost|workspace cleanup failed|ci job failed", re.I),
        "weight": 4,
        "cause": "The container, CI runner, workspace, or image lifecycle failed before the intended task completed.",
        "remediation": "Inspect the first runner/container error, image digest, workspace limits, and the exact CI step that failed.",
        "missing": "The runner image, CI step metadata, environment, and first container error are incomplete.",
    },
    {
        "failure_type": "concurrency-or-state",
        "signal_id": "deadlock-or-race",
        "pattern": re.compile(r"deadlock|race condition|data race|lock timeout|concurrent modification|optimistic lock", re.I),
        "weight": 4,
        "cause": "The failure indicates conflicting concurrent access or an invalid state transition.",
        "remediation": "Capture the involved operation order and state transition, then isolate the smallest reproducible concurrent case.",
        "missing": "The thread/task timeline, shared resource, and state transition history are incomplete.",
    },
)


def _redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _bounded_log(log: str) -> tuple[str, bool]:
    redacted = _redact(log or "")
    return redacted[:_MAX_LOG_CHARS], len(redacted) > _MAX_LOG_CHARS


def _evidence_lines(log: str, pattern: re.Pattern[str]) -> list[str]:
    return [line.strip() for line in log.splitlines() if pattern.search(line)][:5]


def _confidence(score: int, match_count: int, tied: bool) -> str:
    if tied or match_count == 0 or score < 4:
        return "low"
    if score >= 6:
        return "high"
    return "moderate"


def _diagnosis(log: str) -> dict[str, Any]:
    bounded, truncated = _bounded_log(log)
    if not bounded.strip():
        return _result("unknown", "No failure output was provided.", "low", [], [], [], ["The first error and surrounding context are missing."], truncated)

    matches: list[dict[str, Any]] = []
    for rule in _RULES:
        if rule["pattern"].search(bounded):
            matches.append({
                "failure_type": rule["failure_type"],
                "signal_id": rule["signal_id"],
                "weight": rule["weight"],
                "cause": rule["cause"],
                "remediation": rule["remediation"],
                "missing": rule["missing"],
                "evidence": _evidence_lines(bounded, rule["pattern"]),
            })

    if not matches:
        return _result(
            "unknown",
            "The supplied output does not match a supported failure signature.",
            "low",
            [],
            [],
            ["Provide the first error and its surrounding context.", "Identify the command, runtime, service, and expected outcome."],
            ["The command, environment, expected outcome, and first causal error are missing."],
            truncated,
        )

    by_type: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        by_type.setdefault(match["failure_type"], []).append(match)
    ranked = sorted(by_type.items(), key=lambda item: sum(signal["weight"] for signal in item[1]), reverse=True)
    top_type, top_signals = ranked[0]
    top_score = sum(signal["weight"] for signal in top_signals)
    tied = len(ranked) > 1 and sum(signal["weight"] for signal in ranked[1][1]) == top_score
    confidence = _confidence(top_score, len(top_signals), tied)
    evidence = list(dict.fromkeys(item for signal in top_signals for item in signal["evidence"]))
    hypotheses = []
    for index, (failure_type, signals) in enumerate(ranked, start=1):
        score = sum(signal["weight"] for signal in signals)
        hypotheses.append({
            "id": f"H{index}",
            "failure_type": failure_type,
            "score": score,
            "confidence": _confidence(score, len(signals), tied and index == 1),
            "signal_ids": [signal["signal_id"] for signal in signals],
            "statement": signals[0]["cause"],
            "supporting_evidence": list(dict.fromkeys(item for signal in signals for item in signal["evidence"])),
        })
    remediation = list(dict.fromkeys(signal["remediation"] for signal in top_signals))
    remediation.append("Rerun the smallest relevant check after a reviewed change; do not treat a suggestion as verified.")
    missing = list(dict.fromkeys(signal["missing"] for signal in top_signals))
    if tied:
        missing.append("Multiple failure categories have equal deterministic scores; provide more context before choosing a fix.")
    independent_support = len(top_signals) >= 2 and len(evidence) >= 2 and not tied
    evidence_assessment = {
        "conclusion": "probable_cause" if independent_support else "observed_failure_only",
        "root_cause_status": "unconfirmed",
        "root_cause_confidence": "moderate" if independent_support else "low",
        "sources": ["failure_log"],
        "independent_signal_count": len(top_signals),
        "evidence_line_count": len(evidence),
        "basis": "Multiple matching signals support a probable cause, but only a follow-up result can verify recovery." if independent_support else "The output supports the failure category but does not independently establish its root cause.",
    }
    return _result(
        top_type,
        f"The strongest deterministic evidence indicates a {top_type} failure.",
        confidence,
        evidence,
        hypotheses,
        remediation,
        missing,
        truncated,
        {"matched_signals": [signal["signal_id"] for signal in matches], "scores": {key: sum(signal["weight"] for signal in value) for key, value in ranked}},
        evidence_assessment,
    )


def _result(
    failure_type: str,
    summary: str,
    confidence: str,
    evidence: list[str],
    hypotheses: list[dict[str, Any]],
    remediation: list[str],
    missing_evidence: list[str],
    truncated: bool,
    scoring: dict[str, Any] | None = None,
    evidence_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assessment = evidence_assessment or {
        "conclusion": "insufficient_evidence" if failure_type == "unknown" else "observed_failure_only",
        "root_cause_status": "unconfirmed",
        "root_cause_confidence": "low",
        "sources": ["failure_log"] if evidence else [],
        "basis": "A failure signal is not proof of its root cause.",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "failure_type": failure_type,
        "summary": summary,
        "confidence": confidence,
        "evidence": evidence,
        "hypotheses": hypotheses,
        "scoring": scoring or {"matched_signals": [], "scores": {}},
        "evidence_assessment": assessment,
        "remediation_plan": remediation,
        "missing_evidence": missing_evidence,
        "verification": {
            "status": "pending",
            "reason": "No post-change build, test, or runtime result was supplied.",
            "safe_check": remediation[-1] if remediation else "Rerun the smallest relevant check after review.",
        },
        "verification_status": "pending",
        "input_truncated": truncated,
        "guardrails": [
            "Read-only analysis; no commands, network calls, file writes, or automatic fixes.",
            "Evidence is redacted before it is returned to the client.",
            "Confidence is capped when signals are tied, weak, or incomplete.",
        ],
    }


def _safe_root(project_path: str) -> Path | None:
    root = Path(project_path).expanduser().resolve()
    if not root.is_dir():
        return None
    allowed = os.getenv("BUILD_DOCTOR_ALLOWED_ROOT")
    if allowed:
        try:
            root.relative_to(Path(allowed).expanduser().resolve())
        except ValueError:
            return None
    return root


@mcp.tool()
def analyze_failure(log: str) -> str:
    """Score deterministic signals in sanitized failure output and return JSON."""
    return json.dumps(_diagnosis(log), indent=2)


def _find_value(payload: Any, names: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower().replace("-", "_") in names and isinstance(value, (str, int, float, bool)):
                return value
        for value in payload.values():
            found = _find_value(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_value(value, names)
            if found is not None:
                return found
    return None


def _normalize_alert(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(_find_value(payload, {"event_type", "event", "type", "alert_type", "condition_type"}) or "unknown").lower()
    metric = str(_find_value(payload, {"metric", "metric_name", "signal", "policy_name", "condition_name"}) or "unknown")
    normalized = {
        "provider": provider or "unknown",
        "event_type": event_type,
        "service": _find_value(payload, {"service", "service_name", "entity", "application", "app_name"}),
        "environment": _find_value(payload, {"environment", "env", "stage"}),
        "metric": metric,
        "value": _find_value(payload, {"value", "observed_value", "current_value", "actual"}),
        "threshold": _find_value(payload, {"threshold", "threshold_value", "critical_threshold", "limit"}),
        "unit": _find_value(payload, {"unit", "units"}),
        "condition": str(_find_value(payload, {"condition", "operator", "comparison"}) or "above").lower(),
        "timestamp": _find_value(payload, {"timestamp", "occurred_at", "opened_at", "created_at"}),
        "correlation_id": _find_value(payload, {"correlation_id", "trace_id", "incident_id", "alert_id"}),
    }
    return {key: _redact(str(value)) if value is not None else None for key, value in normalized.items()}


def _alert_breached(alert: dict[str, Any]) -> bool | None:
    try:
        value = float(alert["value"])
        threshold = float(alert["threshold"])
    except (TypeError, ValueError):
        return None
    condition = alert.get("condition", "above")
    if condition in {"above", "greater_than", ">"}:
        return value > threshold
    if condition in {"at_or_above", "greater_than_or_equal", ">="}:
        return value >= threshold
    if condition in {"below", "less_than", "<"}:
        return value < threshold
    if condition in {"at_or_below", "less_than_or_equal", "<="}:
        return value <= threshold
    return None


@mcp.tool()
def analyze_alert(provider: str, payload: str, supporting_log: str = "") -> str:
    """Normalize an observability alert and return deterministic evidence collection guidance."""
    bounded_payload, truncated = _bounded_log(payload)
    try:
        parsed = json.loads(bounded_payload)
    except json.JSONDecodeError:
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "payload must be valid JSON", "guardrails": ["No provider API was called."]})
    if not isinstance(parsed, dict):
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "payload must be a JSON object", "guardrails": ["No provider API was called."]})
    alert = _normalize_alert(provider, parsed)
    event_type = alert["event_type"]
    category_map = {
        "latency": ("runtime-or-api", "alert-latency-threshold", "Latency crossed a configured threshold; the alert does not identify the causal component."),
        "error_rate": ("runtime-or-api", "alert-error-rate-threshold", "Error rate crossed a configured threshold; correlate requests and deployments before choosing a cause."),
        "availability": ("runtime-or-api", "alert-availability-threshold", "Availability breached a threshold; determine whether the cause is dependency, network, deployment, or capacity related."),
        "saturation": ("resource-exhaustion", "alert-resource-saturation", "A resource saturation signal breached a threshold; identify the constrained resource and workload."),
        "deployment": ("container-or-ci", "alert-deployment-change", "A deployment event is present and may be a change correlation point, not proof of causation."),
        "security": ("permissions-or-access", "alert-security-event", "A security or access alert requires identity, resource, and policy evidence before remediation."),
        "certificate": ("network-or-tls", "alert-certificate-expiry", "A certificate signal requires endpoint and certificate-chain evidence."),
        "queue_lag": ("resource-exhaustion", "alert-queue-lag", "Queue lag indicates a throughput or consumer-capacity problem until corroborated."),
    }
    failure_type, signal_id, statement = category_map.get(event_type, ("unknown", "alert-unknown-type", "The alert type is not recognized; do not infer a root cause from provider metadata alone."))
    breach = _alert_breached(alert)
    log_result = _diagnosis(supporting_log) if supporting_log else None
    evidence = [f"Alert provider: {provider or 'unknown'}", f"Alert event type: {event_type}", f"Metric: {alert['metric']}"]
    if breach is not None:
        evidence.append(f"Threshold comparison: value {alert['value']} {alert['condition']} threshold {alert['threshold']} = {breach}.")
    if log_result and log_result["evidence"]:
        evidence.extend(f"Supporting log: {line}" for line in log_result["evidence"])
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "alert_contract_version": "1.0",
        "alert": alert,
        "trigger": {"breached": breach, "signal_id": signal_id},
        "diagnosis": {
            "failure_type": failure_type,
            "statement": statement,
            "confidence": "low" if failure_type == "unknown" or breach is not True else "moderate",
            "evidence": evidence,
            "root_cause_status": "unconfirmed",
            "missing_evidence": ["Correlated traces, logs, deployment changes, and dependency health are required before root-cause attribution."],
        },
        "next_evidence": [
            "Collect a bounded time window of correlated traces and structured logs.",
            "Compare the alert window with deployment/configuration changes.",
            "Check dependent service health and resource saturation using the observability provider.",
        ],
        "action_policy": "notify_and_collect_evidence_only",
        "input_truncated": truncated,
        "guardrails": [
            "Provider-neutral webhook analysis; no provider API was called.",
            "No production command, remediation, rollback, or alert mutation is performed.",
            "A threshold breach is not proof of a root cause.",
        ],
    }, indent=2)


@mcp.tool()
def inspect_ci_annotations(log: str) -> str:
    """Extract provider-neutral error annotations from CI output without executing a job."""
    bounded, truncated = _bounded_log(log)
    annotations: list[dict[str, Any]] = []
    patterns = (
        re.compile(r"##\[(error|warning|notice)\]\s*(.*)", re.I),
        re.compile(r"(?i)\b(error|warning|notice)\s*:\s*(.*)"),
    )
    for line_number, line in enumerate(bounded.splitlines(), start=1):
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                annotations.append({"level": match.group(1).lower(), "message": _redact(match.group(2).strip()), "line": line_number})
                break
        if len(annotations) >= 50:
            break
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "annotations": annotations,
        "count": len(annotations),
        "input_truncated": truncated,
        "guardrails": ["Text extraction only; no CI provider was called and no job was rerun."],
    }, indent=2)


@mcp.tool()
def inspect_api_error(payload: str) -> str:
    """Normalize a sanitized JSON API error envelope into stable evidence."""
    bounded, truncated = _bounded_log(payload)
    try:
        parsed = json.loads(bounded)
    except json.JSONDecodeError:
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "payload must be valid JSON"})
    if not isinstance(parsed, dict):
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "payload must be a JSON object"})
    status = _find_value(parsed, {"status", "status_code", "http_status", "code"})
    message = _find_value(parsed, {"message", "error", "detail", "description", "title"})
    request_id = _find_value(parsed, {"request_id", "requestid", "trace_id", "correlation_id"})
    retry_after = _find_value(parsed, {"retry_after", "retryafter"})
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "message": _redact(str(message)) if message is not None else None,
        "request_id": _redact(str(request_id)) if request_id is not None else None,
        "retry_after": retry_after,
        "evidence": [item for item in (f"HTTP status: {status}" if status is not None else None, f"Error message: {_redact(str(message))}" if message is not None else None) if item],
        "input_truncated": truncated,
        "guardrails": ["Sanitized envelope inspection only; no retry, network request, or credential handling was performed."],
    }, indent=2)


@mcp.tool()
def inspect_project(project_path: str) -> str:
    """Read bounded, redacted metadata from root project manifests without executing code."""
    root = _safe_root(project_path)
    if root is None:
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "project_path is missing, invalid, or outside BUILD_DOCTOR_ALLOWED_ROOT"})
    manifests: list[str] = []
    sections: list[str] = []
    for name in _MANIFESTS:
        path = root / name
        if not path.is_file() or path.is_symlink():
            continue
        try:
            manifests.append(name)
            if path.stat().st_size > _MAX_FILE_BYTES:
                sections.append(f"--- {name} ---\n[file skipped: exceeds size limit]")
                continue
            content = _redact(path.read_text(encoding="utf-8", errors="replace")[:_MAX_FILE_BYTES])
            sections.append(f"--- {name} ---\n{content}")
        except OSError as exc:
            sections.append(f"--- {name} ---\n[file unavailable: {exc}]")
    return json.dumps({"schema_version": SCHEMA_VERSION, "project_path": str(root), "manifests": manifests, "content": "\n\n".join(sections), "guardrails": ["Root-level allowlisted manifests only; no symlinks, recursion, execution, or writes."]}, indent=2)


def _report_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("*.xml", "surefire-reports/*.xml", "test-results/*.xml", "test-results/**/*.xml", "reports/**/*.xml"):
        candidates.extend(root.glob(pattern))
    return sorted({path for path in candidates if path.is_file() and not path.is_symlink()})[:_MAX_REPORTS]


def _integer_attribute(element: Any, name: str) -> int:
    try:
        return max(int(element.attrib.get(name, "0")), 0)
    except (TypeError, ValueError):
        return 0


@mcp.tool()
def inspect_test_reports(project_path: str) -> str:
    """Parse bounded JUnit, Surefire, or pytest-style XML reports without executing tests."""
    root = _safe_root(project_path)
    if root is None:
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "project_path is missing, invalid, or outside BUILD_DOCTOR_ALLOWED_ROOT"})
    reports: list[dict[str, Any]] = []
    for path in _report_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                reports.append({"path": relative, "status": "skipped", "reason": "exceeds size limit"})
                continue
            document = SafeElementTree.parse(path)
            root_element = document.getroot()
            suites = [root_element] if root_element.tag.endswith("testsuite") else list(root_element.iter("testsuite"))
            failures: list[dict[str, str]] = []
            totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
            for suite in suites:
                for key in totals:
                    totals[key] += _integer_attribute(suite, key)
                for case in suite.iter("testcase"):
                    issue = next((child for child in case if child.tag in {"failure", "error"}), None)
                    if issue is not None and len(failures) < 20:
                        failures.append({
                            "test": _redact(f"{case.attrib.get('classname', '')}.{case.attrib.get('name', '')}"),
                            "kind": issue.tag,
                            "message": _redact(issue.attrib.get("message", "") or (issue.text or "")[:1000]),
                        })
            reports.append({"path": relative, "status": "parsed", **totals, "failing_tests": failures})
        except (OSError, SafeElementTree.ParseError, ValueError) as exc:
            reports.append({"path": relative, "status": "unreadable", "reason": type(exc).__name__})
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "project_path": str(root),
        "reports": reports,
        "guardrails": ["XML is parsed with defusedxml; no external entities, code execution, recursion outside report directories, or writes."],
    }, indent=2)


@mcp.tool()
def summarize_diagnosis(log: str, project_path: str = "") -> str:
    """Combine scored failure analysis and optional project metadata as JSON."""
    project = json.loads(inspect_project(project_path)) if project_path else {"schema_version": SCHEMA_VERSION, "manifests": [], "content": ""}
    reports = json.loads(inspect_test_reports(project_path)) if project_path else {"schema_version": SCHEMA_VERSION, "reports": []}
    return json.dumps({"schema_version": SCHEMA_VERSION, "diagnosis": _diagnosis(log), "project": project, "test_reports": reports}, indent=2)


@mcp.tool()
def verify_resolution(before_log: str, after_log: str) -> str:
    """Compare supplied before/after output without executing a command or claiming unsupported success."""
    before = _diagnosis(before_log)
    after = _diagnosis(after_log)
    after_clean = _redact(after_log or "")
    success_signal = bool(re.search(r"(?i)(build\s+(?:success|passed)|tests?\s+passed|exit(?:ed)?\s+with\s+(?:code\s+)?0|http\s+(?:200|201|204))", after_clean))
    resolved = before["failure_type"] != "unknown" and success_signal and after["failure_type"] == "unknown"
    status = "verified" if resolved else "inconclusive"
    reason = (
        "The before output contained a supported failure and the after output contains a success signal without a supported failure."
        if resolved
        else "The supplied before/after evidence does not prove recovery; inspect the remaining failure or provide a clearer success result."
    )
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "before": {"failure_type": before["failure_type"], "scoring": before["scoring"]},
        "after": {"failure_type": after["failure_type"], "success_signal": success_signal, "scoring": after["scoring"]},
        "guardrails": ["Comparison only; no commands or fixes were executed.", "Verification requires explicit before and after evidence."],
    }, indent=2)


def main() -> None:
    """Start the MCP server over stdio for MCP-compatible clients."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

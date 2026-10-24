"""Deterministic, dependency-free incident signal extraction.

The analyzer never sends logs to external services. ADK only receives short,
redacted excerpts returned by the public tool functions.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

MAX_BYTES = 1_000_000
MAX_LINES = 5000
MAX_EXCERPT = 220

# Intentionally conservative. This is best-effort redaction, not a DLP product.
_REDACTIONS = [
    re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/-]+=*)"),
    re.compile(r"(?i)(\b(?:password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|secret|authorization)\b\s*[:=]\s*[\"']?)([^\s,;\"'}]+)"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)(://[^\s:/@]+:)([^\s/@]+)(@)"),
    re.compile(r"(?i)([?&](?:token|key|secret|password)=)([^\s&#]+)"),
]


@dataclass(frozen=True)
class Signal:
    id: str
    title: str
    regex: re.Pattern[str]
    priority: int
    cause: str
    checks: tuple[str, ...]


SIGNALS: tuple[Signal, ...] = (
    Signal("database_pool_exhaustion", "Database connection pool exhaustion",
           re.compile(r"(?i)hikari.*(?:connection is not available|timeout after)|connection pool.*(?:exhaust|timeout)|too many connections"),
           100, "The application appears unable to acquire database connections from its pool.",
           ("Inspect active/idle/pending database pool metrics.",
            "Check for slow queries, long transactions, or leaked connections.",
            "Review DB maximum connections and recent load changes before increasing pool size.")),
    Signal("out_of_memory", "Memory pressure / out-of-memory",
           re.compile(r"(?i)outofmemoryerror|out of memory|oomkilled|java heap space"),
           95, "The process or runtime may have exceeded its available memory.",
           ("Inspect heap/RSS and container memory limits around the incident.",
            "Check GC pauses, heap dumps, and allocation trends.",
            "Investigate memory leaks before increasing limits.")),
    Signal("disk_full", "Disk space exhausted",
           re.compile(r"(?i)no space left on device|enospc|disk quota exceeded"),
           90, "A filesystem may have run out of writable space.",
           ("Check filesystem free space and inode usage.",
            "Inspect log rotation and recent large file growth.",
            "Clear space safely only after confirming what can be removed.")),
    Signal("connection_refused", "Downstream connection refused",
           re.compile(r"(?i)connection refused|connectexception.*refused|econnrefused"),
           80, "A target service or port may not have been listening or reachable.",
           ("Verify target host, port, and process health.",
            "Check routing, service discovery, and firewall changes.")),
    Signal("dns_failure", "DNS resolution failure",
           re.compile(r"(?i)unknownhostexception|name or service not known|enotfound|getaddrinfo failed"),
           78, "A requested hostname may not be resolving.",
           ("Validate DNS records and resolver health.",
            "Verify the hostname and recent deployment/configuration changes.")),
    Signal("tls_error", "TLS handshake / certificate failure",
           re.compile(r"(?i)sslhandshakeexception|certificate verify failed|certificate has expired|pkix path building failed"),
           77, "A TLS certificate or trust-chain issue may be blocking a connection.",
           ("Check certificate validity dates, SAN, hostname, and trust chain.",
            "Compare the configured trust store with recent certificate rotations.")),
    Signal("downstream_timeout", "Downstream request timeout",
           re.compile(r"(?i)sockettimeoutexception|read timed out|upstream timed out|gateway timeout|504 gateway timeout|deadline exceeded"),
           60, "A dependency or request may be responding too slowly.",
           ("Correlate upstream and downstream latency metrics.",
            "Check dependency saturation and timeout configuration.",
            "Look for an earlier failure that could explain the timeout.")),
    Signal("rate_limited", "Rate limiting / throttling",
           re.compile(r"(?i)429 too many requests|rate limit exceeded|throttlingexception"),
           55, "A service appears to be rejecting requests due to throttling.",
           ("Check quota dashboards and recent request bursts.",
            "Use backoff and jitter; avoid unbounded retry storms.")),
    Signal("auth_failure", "Authentication or authorization failure",
           re.compile(r"(?i)401 unauthorized|403 forbidden|authenticationfailed|invalid credentials|access denied"),
           52, "A request may have failed due to invalid identity or insufficient permissions.",
           ("Check token expiry, principal identity, and recent permission changes.",
            "Avoid printing or sharing access tokens during diagnosis.")),
    Signal("null_pointer", "Null reference exception",
           re.compile(r"(?i)nullpointerexception|attributeerror: 'nonetype'"),
           48, "Application code attempted to access an unavailable value.",
           ("Inspect the stack trace and the first application-owned frame.",
            "Check unexpected null data and input validation.")),
    Signal("service_unavailable", "HTTP 503 service unavailable",
           re.compile(r"(?i)503 service unavailable|\bhttp.?503\b|\bstatus[=: ]+503\b"),
           30, "The request failed because a service reported itself unavailable; it may be a symptom.",
           ("Check service health and capacity.",
            "Look earlier in the log for the triggering fault.")),
)


def redact(text: str) -> str:
    result = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", "[REDACTED_PRIVATE_KEY]", text, flags=re.S)
    result = re.sub(r'''(?i)((?:["']?)(?:password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|secret|authorization|cookie|set-cookie)(?:["']?)\s*[:=]\s*)(["'])(.*?)\2''', r'\1"[REDACTED]"', result)
    result = re.sub(r"(?im)(\b(?:cookie|set-cookie):\s*)[^\r\n]+", r"\1[REDACTED]", result)
    result = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED_JWT]", result)
    for index, pattern in enumerate(_REDACTIONS):
        if index == 2:
            result = pattern.sub("[REDACTED_AWS_KEY]", result)
        elif index == 3:
            result = pattern.sub(r"\1[REDACTED]\3", result)
        else:
            result = pattern.sub(r"\1[REDACTED]", result)
    return result


def _timestamp(line: str) -> str | None:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)\b", line)
    return m.group(1) if m else None


def redacted_lines(text: str) -> list[str]:
    """Suppress whole private-key blocks while preserving original line indices."""
    safe = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
                  lambda m: "\n".join("[REDACTED_PRIVATE_KEY]" for _ in m.group().splitlines()),
                  text, flags=re.S)
    return [redact(line) for line in safe.splitlines()]


def _severity(lines: list[str]) -> str:
    if any(re.search(r"(?i)\b(?:fatal|critical)\b", l) for l in lines):
        return "critical"
    if any(re.search(r"(?i)\b(?:error|exception|failed)\b", l) for l in lines):
        return "error"
    if any(re.search(r"(?i)\bwarn(?:ing)?\b", l) for l in lines):
        return "warning"
    return "unknown"


def analyze_logs(log_text: str) -> dict:
    """Extract redacted, line-numbered diagnostic signals from a log string.

    The output is a hypothesis/evidence bundle, never a verified root cause.
    """
    if not isinstance(log_text, str):
        raise TypeError("log_text must be a string")
    if len(log_text.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"Log text exceeds {MAX_BYTES} bytes")
    if any(ord(c) < 32 and c not in "\r\n\t" for c in log_text):
        raise ValueError("Unsupported control characters; use UTF-8 text logs")
    lines = log_text.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError(f"Log text exceeds {MAX_LINES} lines")

    # Redact before excerpt slicing, including multiline key material.
    safe_lines = redacted_lines(log_text)
    signal_results = []
    timeline = []
    for signal in SIGNALS:
        hits = [(i, line) for i, line in enumerate(lines, start=1) if signal.regex.search(line)]
        if not hits:
            continue
        examples = [
            {"line": n, "timestamp": _timestamp(line), "excerpt": safe_lines[n - 1][:MAX_EXCERPT]}
            for n, line in hits[:3]
        ]
        signal_results.append({
            "id": signal.id, "title": signal.title,
            "count": len(hits), "priority": signal.priority,
            "hypothesis": signal.cause, "evidence": examples,
            "suggested_checks": list(signal.checks),
        })
        first_number, first_line = hits[0]
        timeline.append({
            "line": first_number, "timestamp": _timestamp(first_line),
            "signal": signal.id, "excerpt": safe_lines[first_number - 1][:MAX_EXCERPT],
        })
    signal_results.sort(key=lambda s: (-s["priority"], -s["count"]))
    timeline.sort(key=lambda t: t["line"])
    top = signal_results[0] if signal_results else None
    checks = list(top["suggested_checks"]) if top else [
        "Search for error-level messages and stack traces outside this sample.",
        "Correlate logs with metrics, traces, and recent changes.",
    ]
    return {
        "status": "signals_detected" if top else "no_known_signals",
        "processed_lines": len(lines),
        "severity": _severity(lines),
        "probable_root_cause": top["hypothesis"] if top else None,
        "root_cause_status": "Unverified hypothesis; requires investigation" if top else "Insufficient evidence",
        "top_signals": signal_results[:5],
        "timeline": timeline[:10],
        "suggested_checks": checks,
        "privacy_note": "Returned excerpts are best-effort redacted; review before sharing. No log contents are sent by the offline CLI.",
    }


def read_log_file(path: Path) -> str:
    """Read an explicitly selected local log file under the size cap."""
    if not path.is_file():
        raise ValueError("Not a regular file or file does not exist")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"File exceeds {MAX_BYTES} bytes")
    if path.suffix.lower() not in {".log", ".txt", ".jsonl"}:
        raise ValueError("Unsupported file format; use .log, .txt, or .jsonl UTF-8 text")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"File exceeds {MAX_BYTES} bytes")
    try:
        return data.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Unsupported encoding; use UTF-8 text") from None


def get_runbook(signal_id: str) -> dict:
    """Find a built-in investigation runbook by exact signal ID."""
    for signal in SIGNALS:
        if signal.id == signal_id.strip().lower():
            return {"signal": signal.id, "hypothesis": signal.cause,
                    "checks": list(signal.checks), "note": "Manual verification required; no actions were executed."}
    return {"error": "Unknown signal ID", "known_signals": [s.id for s in SIGNALS]}

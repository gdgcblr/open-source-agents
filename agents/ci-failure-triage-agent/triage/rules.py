"""Pure domain rules. No I/O, no network, no framework imports."""
import re
from typing import Optional

from .models import Category, TestFailure, Verdict

INFRA_PATTERNS = [
    (r"connection (reset|refused|timed out)", "network connection problem"),
    (r"could not resolve host|name or service not known|temporary failure in name resolution", "DNS failure"),
    (r"service unavailable|bad gateway|gateway time-?out", "upstream service unavailable"),
    (r"no space left on device", "runner disk full"),
    (r"out of memory|oomkilled|exit code 137", "runner out of memory"),
    (r"toomanyrequests|rate limit exceeded|429 too many requests", "rate limited by external service"),
    (r"received a shutdown signal|lost communication", "runner lost / preempted"),
    (r"econnreset|etimedout|enotfound", "network error (node)"),
]
ASSERTION_PATTERN = re.compile(r"assertion ?error|expected .* (to|but)|\bassert\b|expected:|actual:", re.I)


def scan_log_for_infra(log_lines: list[str]) -> list[str]:
    """Run-level infra signals with line numbers, e.g. 'log line 42: DNS failure'."""
    hits: list[str] = []
    for i, line in enumerate(log_lines, 1):
        for pat, label in INFRA_PATTERNS:
            if re.search(pat, line, re.I):
                hits.append(f"log line {i}: {label}")
                break
    return hits[:10]


def classify(
    failure: TestFailure,
    log_infra_hits: list[str],
    history: Optional[dict[str, list[str]]] = None,
) -> Optional[Verdict]:
    """Return a Verdict if a rule fires with enough confidence, else None (-> LLM)."""
    text = f"{failure.message}\n{failure.details}"
    has_assertion = bool(ASSERTION_PATTERN.search(text))

    if failure.rerun_passed:  # Rule 1: CI retried it and it passed
        return Verdict(
            category=Category.FLAKY, confidence=0.95,
            evidence=["JUnit records a failed attempt followed by a passing rerun"],
            suggested_action="Quarantine or stabilise this test; check for timing, ordering or shared-state issues.",
        )

    if history and failure.name in history:  # Rule 2: mixed history
        runs = history[failure.name][-10:]
        fails, passes = runs.count("fail"), runs.count("pass")
        if passes >= 1 and fails >= 1 and not has_assertion:
            return Verdict(
                category=Category.FLAKY, confidence=0.8,
                evidence=[f"history: {passes} pass / {fails} fail in last {len(runs)} runs"],
                suggested_action="Intermittent in history; investigate nondeterminism before blaming the latest change.",
            )

    for pat, label in INFRA_PATTERNS:  # Rule 3: infra signature in the failure itself
        if re.search(pat, text, re.I):
            return Verdict(
                category=Category.INFRA, confidence=0.85,
                evidence=[f"failure text matches: {label}"],
                suggested_action="Re-run the job; if it persists, check runner/network/service health.",
            )

    if log_infra_hits and not has_assertion:  # Rule 4: run-level infra signals
        return Verdict(
            category=Category.INFRA, confidence=0.7, evidence=log_infra_hits[:3],
            suggested_action="Environment problem likely; re-run and inspect runner logs.",
        )

    if has_assertion and not log_infra_hits:  # Rule 5: assertion + clean history
        runs = (history or {}).get(failure.name, [])[-10:]
        if runs and all(r == "pass" for r in runs):
            return Verdict(
                category=Category.REGRESSION, confidence=0.85,
                evidence=[f"assertion mismatch; passed {len(runs)}/{len(runs)} previous runs", f"message: {failure.message[:120]}"],
                suggested_action="Likely caused by a recent change: bisect commits touching the code under test.",
            )
    return None

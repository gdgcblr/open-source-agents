"""Deterministic tools used by the Flaky Test Triage agent.

All tools use only the Python standard library, so they can be unit tested
without an API key. The LLM reasons over their structured output.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HISTORY_FILE = Path(__file__).parent / "test_history.json"

# Each rule: (category, verdict, regex patterns, suggested fix)
RULES: list[dict[str, Any]] = [
    {
        "category": "timing_synchronization",
        "verdict": "likely_flaky",
        "patterns": [
            r"TimeoutException",
            r"StaleElementReferenceException",
            r"ElementClickInterceptedException",
            r"ElementNotInteractableException",
            r"Timed out waiting",
            r"waiting for (visibility|element|presence)",
        ],
        "fix": "Replace fixed sleeps with explicit waits on the exact condition "
               "(visibility, clickable, text present). Re-find elements after page "
               "updates to avoid stale references.",
    },
    {
        "category": "environment_infrastructure",
        "verdict": "likely_environment",
        "patterns": [
            r"ConnectException",
            r"Connection refused",
            r"UnknownHostException",
            r"SocketTimeoutException",
            r"\b50[234]\b",
            r"Service Unavailable",
            r"OutOfMemoryError",
            r"No space left on device",
            r"session not created",
        ],
        "fix": "Check the health of the test environment, grid or backend service "
               "before blaming the test. Add a readiness check and a bounded retry "
               "for infrastructure calls only.",
    },
    {
        "category": "test_data_state",
        "verdict": "likely_test_issue",
        "patterns": [
            r"already exists",
            r"duplicate (key|entry)",
            r"\b409\b",
            r"Conflict",
            r"unique constraint",
        ],
        "fix": "Make the test independent: create unique data per run (UUID suffix) "
               "and clean up in teardown, instead of sharing state across tests.",
    },
    {
        "category": "locator_ui_change",
        "verdict": "likely_test_issue",
        "patterns": [
            r"NoSuchElementException",
            r"Unable to locate element",
            r"no such element",
        ],
        "fix": "The locator no longer matches the page. Inspect the current DOM, "
               "prefer stable attributes (data-testid, id) over XPath position.",
    },
    {
        "category": "assertion_product_behavior",
        "verdict": "likely_real_bug",
        "patterns": [
            r"AssertionError",
            r"AssertionFailedError",
            r"expected\s*[\[<(]?.+?[\]>)]?\s*(but|to)\s*(was|found|be|equal)",
            r"Expected status code",
        ],
        "fix": "Deterministic assertion mismatch. Verify the expected value against "
               "the requirement, then investigate the product change that caused it.",
    },
]

_ERROR_LINE = re.compile(
    r"(?P<type>(?:[a-zA-Z_][\w]*\.)*[A-Z][\w]*(?:Exception|Error|Failure))"
    r"(?::\s*(?P<msg>.*))?"
)
_JAVA_TEST = re.compile(r"(?:FAILED|FAIL|Failed tests?:?|\[ERROR\])\s*:?\s*"
                        r"(?P<name>[A-Z]\w+\.\w+)")
_PY_TEST = re.compile(r"(?P<name>[\w/\.]+\.py::\w+)")


def parse_test_log(log_text: str) -> dict:
    """Extract the key facts from a raw test failure log.

    Args:
        log_text: The full text of a failing test log (Selenium, REST Assured,
            pytest, Jenkins console output, etc.).

    Returns:
        A dict with framework, test_name, error_type, error_message and
        stack_excerpt. Fields that cannot be found are set to "unknown".
    """
    text = log_text or ""
    lower = text.lower()

    if "selenium" in lower or "webdriver" in lower:
        framework = "selenium"
    elif "restassured" in lower or "rest-assured" in lower or "io.restassured" in lower:
        framework = "rest-assured"
    elif "pytest" in lower or ".py::" in lower:
        framework = "pytest"
    elif "testng" in lower or "junit" in lower:
        framework = "java-test-runner"
    else:
        framework = "unknown"

    test_name = "unknown"
    m = _JAVA_TEST.search(text) or _PY_TEST.search(text)
    if m:
        test_name = m.group("name")

    error_type, error_message = "unknown", "unknown"
    for line in text.splitlines():
        em = _ERROR_LINE.search(line)
        if em:
            error_type = em.group("type").split(".")[-1]
            error_message = (em.group("msg") or "").strip() or "unknown"
            break

    stack = [ln.strip() for ln in text.splitlines()
             if ln.strip().startswith("at ") or "Traceback" in ln or ln.strip().startswith("File ")]
    return {
        "framework": framework,
        "test_name": test_name,
        "error_type": error_type,
        "error_message": error_message[:300],
        "stack_excerpt": stack[:5],
    }


def classify_failure(log_text: str) -> dict:
    """Classify a failure into a root-cause category using keyword rules.

    Args:
        log_text: The full text of the failing test log.

    Returns:
        A dict with category, verdict (likely_flaky, likely_environment,
        likely_test_issue, likely_real_bug or unclear), confidence (0 to 1),
        matched evidence and a suggested_fix.
    """
    text = log_text or ""
    best: dict[str, Any] | None = None
    best_hits: list[str] = []
    for rule in RULES:
        hits = [p for p in rule["patterns"] if re.search(p, text, re.IGNORECASE)]
        if len(hits) > len(best_hits):
            best, best_hits = rule, hits
    if not best:
        return {
            "category": "unclear",
            "verdict": "unclear",
            "confidence": 0.2,
            "evidence": [],
            "suggested_fix": "No known pattern matched. Reproduce locally and "
                             "collect more logs, screenshots and network traces.",
        }
    confidence = min(0.5 + 0.15 * len(best_hits), 0.95)
    return {
        "category": best["category"],
        "verdict": best["verdict"],
        "confidence": round(confidence, 2),
        "evidence": best_hits,
        "suggested_fix": best["fix"],
    }


def check_flakiness_history(test_name: str) -> dict:
    """Look up a test's recent pass/fail history to measure flakiness.

    Args:
        test_name: The test identifier, e.g. "LoginTest.testLoginWithValidUser".

    Returns:
        A dict with runs, pass_rate, flips (pass/fail alternations) and a
        history_verdict: flaky, consistently_failing, stable or no_history.
    """
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    entry = data.get(test_name)
    if not entry or not entry.get("runs"):
        return {"test_name": test_name, "history_verdict": "no_history",
                "runs": [], "pass_rate": None, "flips": 0}
    runs = entry["runs"]
    passes = runs.count("pass")
    flips = sum(1 for a, b in zip(runs, runs[1:]) if a != b)
    pass_rate = round(passes / len(runs), 2)
    if flips >= 3 and 0.2 <= pass_rate <= 0.9:
        verdict = "flaky"
    elif runs[-3:] == ["fail"] * 3 or pass_rate <= 0.2:
        verdict = "consistently_failing"
    else:
        verdict = "stable"
    return {"test_name": test_name, "runs": runs, "pass_rate": pass_rate,
            "flips": flips, "history_verdict": verdict}


def combine_signals(classification: dict, history: dict) -> dict:
    """Merge the log classification and run history into one final verdict.

    Args:
        classification: Output of classify_failure.
        history: Output of check_flakiness_history.

    Returns:
        A dict with final_verdict (flaky, real_bug, environment_issue,
        test_issue or needs_investigation), confidence and a short reason.
    """
    v = classification.get("verdict", "unclear")
    h = history.get("history_verdict", "no_history")
    conf = classification.get("confidence", 0.2)

    if h == "flaky":
        return {"final_verdict": "flaky", "confidence": round(min(conf + 0.2, 0.98), 2),
                "reason": "Test flips between pass and fail across recent runs."}
    if h == "consistently_failing":
        return {"final_verdict": "real_bug" if v in ("likely_real_bug", "unclear")
                else "test_issue",
                "confidence": round(min(conf + 0.15, 0.98), 2),
                "reason": "Test fails consistently, so it is not random flakiness."}
    if v == "likely_environment":
        return {"final_verdict": "environment_issue", "confidence": conf,
                "reason": "Failure points to infrastructure, not test logic."}
    if v == "likely_flaky":
        return {"final_verdict": "flaky", "confidence": conf,
                "reason": "Timing pattern in the log. History is stable or missing."}
    if v == "likely_real_bug":
        return {"final_verdict": "real_bug", "confidence": conf,
                "reason": "Deterministic assertion mismatch."}
    if v == "likely_test_issue":
        return {"final_verdict": "test_issue", "confidence": conf,
                "reason": "Locator or test data problem in the test itself."}
    return {"final_verdict": "needs_investigation", "confidence": conf,
            "reason": "No strong signal from log or history."}

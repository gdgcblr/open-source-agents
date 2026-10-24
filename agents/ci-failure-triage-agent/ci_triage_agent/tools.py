"""Read-only ADK function tools. Every string leaving a tool is redacted first, so the
model never sees secrets. File access is confined to TRIAGE_ROOT (default: current directory)."""
import json
import os
from pathlib import Path

from triage.adapters.files import load_run, parse_junit, read_log
from triage.privacy import redact
from triage.service import apply_rules, pii_counts


def _root() -> Path:
    return Path(os.environ.get("TRIAGE_ROOT", ".")).resolve()


def _safe_path(path: str) -> Path:
    p = (_root() / path).resolve() if not os.path.isabs(path) else Path(path).resolve()
    if not p.is_relative_to(_root()):
        raise ValueError(f"path '{path}' is outside the allowed directory")
    if p.suffix.lower() not in {".xml", ".log", ".txt", ".json"}:
        raise ValueError("unsupported file type")
    if not p.is_file():
        raise ValueError(f"file not found: {path}")
    return p


def _clean(obj):
    """Recursively redact every string in a JSON-like structure."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, list):
        return [_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    return obj


def classify_with_rules(junit_path: str, log_path: str = "", history_path: str = "") -> dict:
    """Parse a JUnit XML report and classify every failing test with deterministic rules.

    Args:
        junit_path: Path to the JUnit XML file, relative to the working directory.
        log_path: Optional path to the raw CI log.
        history_path: Optional path to a JSON file like {"test_name": ["pass", "fail", ...]}.

    Returns:
        A dict with total_tests and a list of failures. Each failure has a "rule_verdict"
        (category, confidence, evidence, suggested_action) or null when no rule matched
        and the failure needs your own analysis.
    """
    try:
        run = load_run(
            str(_safe_path(junit_path)),
            str(_safe_path(log_path)) if log_path else None,
            str(_safe_path(history_path)) if history_path else None,
        )
    except (ValueError, OSError, json.JSONDecodeError) as e:
        return {"error": redact(str(e))}
    out = [
        {
            "test": f"{f.classname}.{f.name}" if f.classname else f.name,
            "name": f.name,
            "message": f.message,
            "rule_verdict": json.loads(v.model_dump_json()) if v else None,
        }
        for f, v in apply_rules(run)
    ]
    return _clean({"total_tests": run.total_tests, "failures": out, "pii_found_counts": pii_counts(run)})


def get_failure_details(junit_path: str, test_name: str) -> dict:
    """Return the message and stack trace of one failing test (use for tests with no rule verdict).

    Args:
        junit_path: Path to the JUnit XML file.
        test_name: The "name" field of the failing test as returned by classify_with_rules.

    Returns:
        A dict with message and details (truncated), or an error.
    """
    try:
        failures, _ = parse_junit(str(_safe_path(junit_path)))
    except (ValueError, OSError) as e:
        return {"error": redact(str(e))}
    for f in failures:
        if f.name == test_name:
            return _clean({"name": f.name, "message": f.message, "details": f.details[:3000]})
    return {"error": f"no failing test named '{test_name}'"}


def get_log_context(log_path: str, test_name: str, width: int = 3) -> dict:
    """Return up to 40 log lines around mentions of a test name.

    Args:
        log_path: Path to the raw CI log.
        test_name: The "name" field of the failing test.
        width: Lines of context before and after each mention (max 5).

    Returns:
        A dict with the matching log lines, or an error.
    """
    try:
        lines = read_log(str(_safe_path(log_path)))
    except (ValueError, OSError) as e:
        return {"error": redact(str(e))}
    width = max(0, min(width, 5))
    out: list[str] = []
    for i, line in enumerate(lines):
        if test_name in line:
            out += lines[max(0, i - width) : i + width + 1]
        if len(out) >= 40:
            break
    return _clean({"lines": out[:40]})

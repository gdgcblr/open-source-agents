"""Safe, lightweight tools callable by a Google ADK agent."""
import os
from pathlib import Path
from .engine import analyze_logs, read_log_file, get_runbook

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG_ROOT = _PROJECT_ROOT / "samples"


def triage_log_text(log_text: str) -> dict:
    """Analyze pasted application log text and return line-numbered, redacted evidence.

    Args:
        log_text: The user's log excerpt (up to 1 MB and 5000 lines).

    Returns:
        Structured incident hypotheses, evidence, timeline, and next checks.
    """
    try:
        return analyze_logs(log_text)
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}


def triage_log_file(filename: str) -> dict:
    """Analyze a file in the approved local logs directory (read-only).

    Args:
        filename: A log filename relative to the allowed log directory, e.g. spring-boot-incident.log.

    Returns:
        Structured, redacted incident investigation evidence.
    """
    root = Path(os.getenv("TRIAGE_LOG_DIR", str(_DEFAULT_LOG_ROOT))).expanduser().resolve()
    try:
        target = (root / filename).resolve()
        if not target.is_relative_to(root) or target == root:
            return {"error": "Path is outside the allowed log directory"}
        text = read_log_file(target)
        result = analyze_logs(text)
        result["source_file"] = target.name
        return result
    except (ValueError, OSError, UnicodeError) as exc:
        return {"error": str(exc)}


def incident_runbook(signal_id: str) -> dict:
    """Return safe, non-executing investigation steps for a known signal.

    Args:
        signal_id: A signal identifier from triage results, such as database_pool_exhaustion.

    Returns:
        Recommended human-verifiable checks and the signal's description.
    """
    return get_runbook(signal_id)

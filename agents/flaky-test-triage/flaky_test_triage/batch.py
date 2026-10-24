"""Batch triage, failure clustering and report generation.

Fully deterministic (no LLM call per log), so a folder of 200 logs is instant
and does not burn API quota. Run it without any API key:

    python -m flaky_test_triage.batch sample_batch
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .guardrails import sanitize_input
from .reporting import format_message, write_reports
from .tools import check_flakiness_history, classify_failure, combine_signals, parse_test_log

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_FILES = 200
MAX_FILE_BYTES = 200_000
LOG_SUFFIXES = {".log", ".txt"}


def safe_path(user_path: str, must_be_dir: bool) -> Path:
    """Resolve a path and make sure it stays inside the project folder."""
    if not isinstance(user_path, str) or not user_path.strip() or len(user_path) > 300 or "\x00" in user_path:
        raise ValueError("invalid path")
    p = Path(user_path.strip())
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p = p.resolve()
    try:
        rel = p.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError("path must be inside the project folder") from None
    if any(part.startswith(".") for part in rel.parts):
        raise ValueError("hidden files and folders are not allowed")
    if must_be_dir and not p.is_dir():
        raise ValueError(f"folder not found: {rel}")
    if not must_be_dir and not p.is_file():
        raise ValueError(f"file not found: {rel}")
    return p


_FACTOR_RES = [
    ("node", re.compile(r"\bnode:\s*([\w.\-]+)")),
    ("host", re.compile(r"\b((?:qa|stg|test|uat)-[\w\-]+(?:\.[\w\-]+)*(?::\d+)?)")),
]


def extract_factors(text: str) -> list[str]:
    """Shared infrastructure hints such as a grid node or backend host."""
    found = []
    for kind, pat in _FACTOR_RES:
        for m in pat.finditer(text):
            f = f"{kind}={m.group(1)}"
            if f not in found:
                found.append(f)
    return found


def triage_text(text: str, source: str) -> dict:
    """Triage one log. Guardrails run first (injection check, redaction)."""
    clean, note, _ = sanitize_input(text)
    if clean is None:
        return {"file": source, "skipped": note}
    parsed = parse_test_log(clean)
    cls = classify_failure(clean)
    name = parsed["test_name"] if parsed["test_name"] != "unknown" else Path(source).stem
    hist = check_flakiness_history(name)
    final = combine_signals(cls, hist)
    return {
        "file": source, "test": name, "framework": parsed["framework"],
        "error_type": parsed["error_type"], "error_message": parsed["error_message"],
        "category": cls["category"], "verdict": final["final_verdict"],
        "confidence": final["confidence"], "reason": final["reason"],
        "evidence": cls["evidence"], "suggested_fix": cls["suggested_fix"],
        "history": hist["history_verdict"], "pass_rate": hist["pass_rate"],
        "factors": extract_factors(clean),
    }


_ROOT_CAUSE = {
    "timing_synchronization": "{nt} timed out waiting for UI conditions{on}. Likely a slow node or missing explicit waits.",
    "environment_infrastructure": "{nt} hit infrastructure errors{on}. Fix the environment once instead of editing {nt}.",
    "test_data_state": "{nt} collide on shared test data{on}. Use unique data per run.",
    "locator_ui_change": "{nt} use locators that no longer match the UI{on}.",
    "assertion_product_behavior": "{nt} fail on a deterministic value mismatch{on}. Check what changed in the product.",
    "unclear": "{nf} matched no known pattern{on}.",
}
_RECOMMENDATION = {
    "timing_synchronization": "Add explicit waits and check the health of {where}",
    "environment_infrastructure": "Check {where} before rerunning. This is not a test bug",
    "test_data_state": "Generate unique test data per run and clean up in teardown",
    "locator_ui_change": "Update the locators and ask devs for stable data-testid attributes",
    "assertion_product_behavior": "Verify expected values against requirements, then raise a bug if the product changed",
    "unclear": "Collect more logs, screenshots and network traces",
}


def cluster_results(results: list[dict]) -> list[dict]:
    """Group failures by (category, error type, shared infrastructure factor)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in results:
        factor = r["factors"][0] if r["factors"] else ""
        groups[(r["category"], r["error_type"], factor)].append(r)

    total = max(len(results), 1)
    clusters = []
    for (category, error_type, factor), members in groups.items():
        n = len(members)
        on = f" on {factor}" if factor else ""
        verdict = Counter(m["verdict"] for m in members).most_common(1)[0][0]
        clusters.append({
            "category": category, "error_type": error_type, "factor": factor or None,
            "size": n, "percent": round(n * 100 / total), "verdict": verdict,
            "tests": sorted(m["test"] for m in members),
            "root_cause": _ROOT_CAUSE.get(category, _ROOT_CAUSE["unclear"]).format(
                nt=f"{n} test{'s' if n != 1 else ''}", nf=f"{n} failure{'s' if n != 1 else ''}", on=on),
            "recommendation": _RECOMMENDATION.get(category, _RECOMMENDATION["unclear"]).format(
                where=factor or "the grid and environment"),
            "representative_message": members[0]["error_message"],
        })
    clusters.sort(key=lambda c: (-c["size"], c["category"]))
    for i, c in enumerate(clusters, 1):
        c["id"] = f"C{i}"
    by_test = {t: c["id"] for c in clusters for t in c["tests"]}
    for r in results:
        r["cluster"] = by_test.get(r["test"], "")
    return clusters


def triage_log_text(log_text: str, name: str = "uploaded.log") -> dict:
    """Triage ONE pasted or uploaded log and return verdict, evidence and fix advice.

    Args:
        log_text: The full text of a failing test log.
        name: Optional file name, used as a label.

    Returns:
        A dict with test, verdict, confidence, category, reason, evidence,
        suggested_fix and run history. Returns {"error": "..."} if the input is blocked.
    """
    r = triage_text(log_text, str(name)[:100])
    if "skipped" in r:
        return {"error": r["skipped"]}
    keys = ("test", "framework", "verdict", "confidence", "category", "reason", "evidence",
            "suggested_fix", "history", "pass_rate", "factors")
    return {k: r[k] for k in keys}


def run_batch_triage(folder: str = "sample_batch") -> dict:
    """Triage every .log or .txt file in a folder, cluster the failures and write reports.

    Args:
        folder: A folder inside the project that holds failing test logs,
            for example "sample_batch".

    Returns:
        A dict with summary counts, root-cause clusters, per-test verdicts,
        the file paths of the HTML dashboard, and ready-to-paste Slack and
        Teams messages. On a bad path it returns {"error": "..."}.
    """
    try:
        d = safe_path(folder, must_be_dir=True)
    except ValueError as e:
        return {"error": str(e)}
    files = sorted(p for p in d.iterdir()
                   if p.is_file() and p.suffix.lower() in LOG_SUFFIXES and not p.name.startswith("."))[:MAX_FILES]
    if not files:
        return {"error": "no .log or .txt files found in that folder"}

    results, skipped = [], []
    for f in files:
        if f.stat().st_size > MAX_FILE_BYTES:
            skipped.append({"file": f.name, "reason": "file too large"})
            continue
        r = triage_text(f.read_text(encoding="utf-8", errors="replace"), f.name)
        (skipped.append({"file": f.name, "reason": r["skipped"]}) if "skipped" in r else results.append(r))

    if not results:
        return {"error": "every file was skipped", "skipped": skipped}

    clusters = cluster_results(results)
    summary = {"total": len(results), "skipped": len(skipped),
               "by_verdict": dict(Counter(r["verdict"] for r in results))}
    paths = write_reports(PROJECT_ROOT / "reports", summary, clusters, results)
    return {
        "summary": summary,
        "clusters": [{k: c[k] for k in ("id", "size", "percent", "verdict", "factor", "root_cause",
                                        "recommendation", "tests")} for c in clusters],
        "tests": [{"test": r["test"], "verdict": r["verdict"], "confidence": r["confidence"],
                   "cluster": r["cluster"]} for r in results],
        "skipped": skipped, "files": paths,
        "slack_message": format_message(summary, clusters, "slack"),
    }


if __name__ == "__main__":
    out = run_batch_triage(sys.argv[1] if len(sys.argv) > 1 else "sample_batch")
    if "error" in out:
        sys.exit(out["error"])
    print(out["slack_message"])
    print("\nWrote:", ", ".join(out["files"].values()))

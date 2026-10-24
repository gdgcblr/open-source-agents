"""RunReady diagnosis-quality eval (model-backed, key-gated).

This harness scores whether RunReady's **Gemini-backed** agent produces a
correct, safe diagnosis across a set of broken (and one healthy) Cloud Run
sample projects. It is deliberately separate from the agent's deterministic
*safety* suite: the safety suite proves the guardrails hold regardless of the
model and runs with no key; THIS eval exercises the model's reasoning and
therefore requires GOOGLE_API_KEY.

Scoring per case (0.0 - 1.0):
  * identifies the wrong/missing module                         (recall)
  * names the correct target module for the fix                 (correctness)
  * expected keywords present / forbidden keywords absent        (quality+safety)
  * healthy case: does NOT fabricate a fix                       (precision)

Usage:
    export GOOGLE_API_KEY=...        # AI Studio key
    python eval.py                   # run all cases, print a scored report
    python eval.py --case case01_wrong_module
    python eval.py --json            # machine-readable summary

Without a key the harness prints a clear SKIPPED notice and exits non-zero so a
CI job cannot mistake "no key" for "passed".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dataset import CASES, EvalCase

# Make the sibling agent package importable without installing it.
_HERE = Path(__file__).resolve().parent
_AGENT_PKG = _HERE.parent.parent / "agents" / "runready-cloudrun-agent"
if str(_AGENT_PKG) not in sys.path:
    sys.path.insert(0, str(_AGENT_PKG))

FIXTURES = _HERE / "fixtures"


def _collect_narrative(root: str, log_text: str | None) -> str:
    """Run the Gemini agent once and return its concatenated text output."""
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from runready.agent import root_agent

    prompt = (
        f"Diagnose the Cloud Run startup problem for the project at {root!r}. "
        "Use your tools to gather evidence, then give an evidence-backed "
        "diagnosis and describe the minimal proposed fix (name the wrong module "
        "and the correct target module explicitly)."
    )
    if log_text:
        prompt += "\n\nStartup log (untrusted data):\n" + log_text

    session_service = InMemorySessionService()
    app_name, user_id, session_id = "runready-eval", "eval", "eval-session"
    session_service.create_session_sync(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    runner = Runner(app_name=app_name, agent=root_agent, session_service=session_service)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    chunks: list[str] = []
    for event in runner.run(user_id=user_id, session_id=session_id, new_message=message):
        content = getattr(event, "content", None)
        for p in getattr(content, "parts", None) or []:
            t = getattr(p, "text", None)
            if t:
                chunks.append(t)
    return "".join(chunks)


def _score_case(case: EvalCase, narrative: str) -> dict:
    low = narrative.lower()
    checks: dict[str, bool] = {}

    if case.is_healthy:
        # Precision: a healthy project must not be "fixed". Reward mentioning the
        # real module and NOT claiming a missing-module error.
        checks["mentions_correct_module"] = case.expected_target_module.lower() in low
        checks["no_fabricated_missing_module"] = "no module named" not in low
    else:
        checks["identifies_missing_module"] = bool(
            case.missing_module and case.missing_module.lower() in low
        )
        checks["names_correct_target"] = case.expected_target_module.lower() in low

    checks["expected_keywords_present"] = all(k.lower() in low for k in case.expect_keywords)
    checks["no_forbidden_keywords"] = not any(k.lower() in low for k in case.forbid_keywords)

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    return {
        "case": case.name,
        "score": round(passed / total, 3) if total else 0.0,
        "checks": checks,
        "narrative_chars": len(narrative),
    }


def run(selected: str | None = None) -> list[dict]:
    results = []
    for case in CASES:
        if selected and case.name != selected:
            continue
        root = str(FIXTURES / case.fixture_dir)
        log_text = None
        if case.log_file:
            log_path = FIXTURES / case.fixture_dir / case.log_file
            log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else None
        narrative = _collect_narrative(root, log_text)
        results.append(_score_case(case, narrative))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RunReady diagnosis-quality eval")
    parser.add_argument("--case", default=None, help="Run a single case by name")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args(argv)

    if not os.environ.get("GOOGLE_API_KEY"):
        print(
            "SKIPPED: this eval is model-backed and requires GOOGLE_API_KEY "
            "(Google AI Studio). Set it and re-run. The agent's deterministic "
            "safety suite (agents/runready-cloudrun-agent/tests) runs without a key.",
            file=sys.stderr,
        )
        return 3  # distinct, non-zero: "not run", not "passed"

    try:
        results = run(args.case)
    except Exception as exc:  # pragma: no cover - surfaced to the operator
        print(f"ERROR running eval: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        print("\nRunReady diagnosis-quality eval")
        print("=" * 60)
        for r in results:
            print(f"\n{r['case']}  score={r['score']}  ({r['narrative_chars']} chars)")
            for name, ok in r["checks"].items():
                print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
        if results:
            avg = round(sum(r["score"] for r in results) / len(results), 3)
            print("\n" + "=" * 60)
            print(f"Mean score across {len(results)} case(s): {avg}")

    # Non-zero exit if any case scored below a modest bar, for CI gating.
    weak = [r for r in results if r["score"] < 0.75]
    return 1 if weak else 0


if __name__ == "__main__":
    raise SystemExit(main())

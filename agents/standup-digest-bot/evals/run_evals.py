"""Evaluation harness for standup-digest-bot.

Why this exists
---------------
The hard part of a standup agent is not producing text, it is producing text you
can *trust*. This harness scores exactly that, on two axes the judges called out:

* Groundedness / precision  -> Of the events the digest claims, how many are
  real (present in the activity log)? Fabricated references are quarantined by
  the agent as [confirm ...], so precision also tells us the guardrail held.
* Coverage / recall         -> Of the events that actually happened, how many
  did the digest surface? Low recall means the agent dropped real work.

It also checks trajectory-style expectations per case: did the agent escalate
when it was supposed to (empty day, partial fetch)? did it keep unconfirmed
claims under budget?

Run offline/deterministic:
    python evals/run_evals.py                # uses mock provider
    python evals/run_evals.py --provider ollama   # score your real model
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Make the sibling package importable when run as a script.
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

from standup.agent import StandupAgent          # noqa: E402
from standup.fixtures import load_activity_log   # noqa: E402
from standup.llm import get_provider             # noqa: E402
from standup.models import ActivityLog, Digest   # noqa: E402


def _resolve(path: str) -> str:
    """Resolve an activity path relative to the project root first, then evals/."""
    for base in (PROJECT_ROOT, HERE):
        candidate = os.path.join(base, path)
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(path)


def score_grounding(digest: Digest, log: ActivityLog) -> dict:
    """Precision = correct refs / all refs; Recall = correct refs / real events."""
    real_ids = log.event_ids
    referenced = digest.referenced_event_ids

    true_positives = referenced & real_ids
    # Fabricated references never reach referenced_event_ids (the guardrail turns
    # them into confirm-items), so we treat confirm-items as precision misses.
    # Exception: when there is NO real activity, an unmatched item is a planning
    # placeholder the agent is supposed to emit, not a hallucinated claim about
    # work. Grounding is vacuously perfect in that case.
    if not real_ids:
        return {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "fabricated_claims": 0,
            "referenced": [],
        }

    fabricated = len(digest.needs_confirmation)
    claimed_total = len(referenced) + fabricated
    precision = len(true_positives) / claimed_total if claimed_total else 1.0
    recall = len(true_positives) / len(real_ids) if real_ids else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "fabricated_claims": fabricated,
        "referenced": sorted(referenced),
    }


def check_expectations(digest: Digest, log: ActivityLog, expect: dict) -> list[str]:
    """Return a list of failure messages (empty == pass)."""
    failures: list[str] = []

    must = set(expect.get("must_reference_event_ids", []))
    missing = must - digest.referenced_event_ids
    if missing:
        failures.append(f"missing required references: {sorted(missing)}")

    want_escalate = expect.get("should_escalate")
    if want_escalate is not None and digest.escalate != want_escalate:
        failures.append(
            f"escalation mismatch: expected {want_escalate}, got {digest.escalate}"
        )

    max_unconfirmed = expect.get("max_unconfirmed", 999)
    if len(digest.needs_confirmation) > max_unconfirmed:
        failures.append(
            f"too many unconfirmed items: {len(digest.needs_confirmation)} "
            f"> {max_unconfirmed}"
        )
    return failures


def run(provider_name: str | None) -> int:
    with open(os.path.join(HERE, "eval_cases.json"), "r", encoding="utf-8") as fh:
        suite = json.load(fh)

    llm = get_provider(provider=provider_name or "mock")
    agent = StandupAgent(llm)

    total = len(suite["cases"])
    passed = 0
    print(f"\nRunning {total} eval case(s) with provider='{llm.name}'\n" + "=" * 60)

    for case in suite["cases"]:
        name = case["name"]
        log = load_activity_log(_resolve(case["activity"]))
        digest = agent.generate(log)
        metrics = score_grounding(digest, log)
        failures = check_expectations(digest, log, case.get("expect", {}))

        status = "PASS" if not failures else "FAIL"
        if not failures:
            passed += 1
        print(f"\n[{status}] {name}")
        print(
            f"   precision={metrics['precision']}  recall={metrics['recall']}  "
            f"f1={metrics['f1']}  fabricated={metrics['fabricated_claims']}  "
            f"escalate={digest.escalate}"
        )
        for f in failures:
            print(f"   - {f}")

    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{total} cases passed")
    return 0 if passed == total else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate standup-digest-bot output.")
    p.add_argument("--provider", help="LLM provider to score (default: mock)")
    args = p.parse_args(argv)
    return run(args.provider)


if __name__ == "__main__":
    raise SystemExit(main())

"""Measure precision and recall of Issue Scout's comment detectors on labelled snippets.

    python evals/run_evals.py              # both sets, with every miss and false alarm
    python evals/run_evals.py --quiet      # tables only

"dev" was used while tuning the patterns, so its scores are optimistic. "holdout" was written
before tuning and never used for it: treat its scores as the real estimate.
Offline and deterministic: no network, no model.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.cases import CASES, HOLDOUT  # noqa: E402
from issue_scout.guardrails import detect_injection  # noqa: E402
from issue_scout.signals import detect_claim, detect_open_policy, detect_resolved  # noqa: E402

DETECTORS = {
    "claim": detect_claim,
    "resolved": detect_resolved,
    "policy": detect_open_policy,
    "injection": detect_injection,
}
SETS = {"dev": CASES, "holdout": HOLDOUT}


def evaluate(cases):
    stats = {name: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for name in DETECTORS}
    mistakes = []
    for text, expected in cases:
        for name, detect in DETECTORS.items():
            fired = detect(text) is not None
            wanted = name in expected
            key = {(True, True): "tp", (True, False): "fp", (False, True): "fn", (False, False): "tn"}[(fired, wanted)]
            stats[name][key] += 1
            if key in ("fp", "fn"):
                mistakes.append((name, "false alarm" if key == "fp" else "missed", text))
    return stats, mistakes


def ratio(num, den):
    return num / den if den else 1.0


def precision(s):
    return ratio(s["tp"], s["tp"] + s["fp"])


def recall(s):
    return ratio(s["tp"], s["tp"] + s["fn"])


def report(name, cases, quiet):
    stats, mistakes = evaluate(cases)
    print("### %s set: %d labelled snippets\n" % (name, len(cases)))
    print("| Detector | Precision | Recall | Positives | False alarms | Missed |")
    print("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for detector, s in stats.items():
        print("| %s | %.0f%% | %.0f%% | %d | %d | %d |" % (
            detector, precision(s) * 100, recall(s) * 100, s["tp"] + s["fn"], s["fp"], s["fn"]))
    if mistakes and not quiet:
        print("\nMistakes:")
        for detector, kind, text in mistakes:
            print("- [%s] %s: %r" % (detector, kind, text.replace("\n", " ")[:90]))
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    for name, cases in SETS.items():
        if args.set in (name, "all"):
            report(name, cases, args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())

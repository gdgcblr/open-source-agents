"""CI gate: turn matrix totals into pass/fail using ci.fail_if."""

from __future__ import annotations

from murphy.config.schema import FailIf


def evaluate(totals: dict, fail_if: FailIf) -> list[str]:
    """Returns the list of tripped conditions (empty = CI passes)."""
    tripped = []
    if fail_if.completion_below is not None and totals["completion"] < fail_if.completion_below:
        tripped.append(f"completion {totals['completion']:.0%} < {fail_if.completion_below:.0%}")
    for label in fail_if.any_label:
        if totals["labels"].get(label):
            tripped.append(f"{totals['labels'][label]} run(s) labelled {label!r}")
    return tripped

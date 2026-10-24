"""Regression gate: detector precision must stay high on both labelled sets.

A false "claimed" or "already fixed" flag hides a good issue from a newcomer, so precision
matters more than recall here. Recall floors are set at today's held-out scores.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.run_evals import SETS, evaluate, precision, recall  # noqa: E402

FLOORS = {  # (min precision, min recall) on the held-out set
    "claim": (0.9, 0.5),
    "resolved": (0.9, 0.7),
    "policy": (0.9, 0.9),
    "injection": (0.9, 0.6),
}


@pytest.mark.parametrize("set_name", sorted(SETS))
def test_detector_precision_and_recall(set_name):
    stats, mistakes = evaluate(SETS[set_name])
    for detector, (min_precision, min_recall) in FLOORS.items():
        s = stats[detector]
        assert precision(s) >= min_precision, (detector, mistakes)
        assert recall(s) >= min_recall, (detector, mistakes)

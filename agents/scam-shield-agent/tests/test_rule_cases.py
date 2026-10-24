"""Runs the shared fixture tests/rule_cases.json against the Python rules.

tests/test_offline_rules.js runs the same file against the browser rules.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scam_shield.tools import rules_verdict  # noqa: E402

CASES = json.loads((Path(__file__).parent / "rule_cases.json").read_text(encoding="utf-8"))["cases"]
ALLOWED = {"safe": {"safe"}, "flagged": {"suspicious", "scam"}, "scam": {"scam"}}


@pytest.mark.parametrize("case", CASES, ids=[f"{i}-{c['gap']}" for i, c in enumerate(CASES)])
def test_shared_rule_case(case):
    verdict = rules_verdict(case["text"], follow_shorteners=False)["verdict"]
    assert verdict in ALLOWED[case["expect"]], f"{case['text']!r} -> {verdict}"

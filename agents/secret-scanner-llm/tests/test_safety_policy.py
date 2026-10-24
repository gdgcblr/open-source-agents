import pytest

from secret_scanner.models import Candidate, TriageResult
from secret_scanner.triage import decide


def cand(hc=False, test=False, sev="critical"):
    return Candidate("f.py", 1, "r", "k", "x****(10 chars, alnum)", [], hc, test, sev)


def tr(v, conf=0.95):
    return TriageResult(v, conf, "because", "fix", "m", 0.1)


@pytest.mark.parametrize("v", ["placeholder", "test_fixture", "false_positive"])
def test_llm_cannot_dismiss_known_format_outside_tests(v):
    f = decide(cand(hc=True, test=False), tr(v, 1.0))
    assert f.verdict == "real" and f.reportable and f.decided_by == "policy"
    assert v in f.llm_note
    assert f.reason == "because"  # explanation still added


def test_known_format_in_test_path_needs_high_confidence():
    assert decide(cand(hc=True, test=True), tr("test_fixture", 0.95)).verdict == "test_fixture"
    f = decide(cand(hc=True, test=True), tr("test_fixture", 0.7))
    assert f.verdict == "uncertain" and f.reportable


def test_non_known_format_can_be_downgraded():
    f = decide(cand(), tr("placeholder", 0.9))
    assert f.verdict == "placeholder" and not f.reportable and f.severity == "info"


def test_low_confidence_dismissal_is_kept():
    f = decide(cand(), tr("false_positive", 0.4))
    assert f.verdict == "uncertain" and f.reportable


def test_real_stays_real_and_no_llm_is_unverified():
    assert decide(cand(), tr("real", 0.8)).verdict == "real"
    f = decide(cand(), None)
    assert f.verdict == "unverified" and f.reportable

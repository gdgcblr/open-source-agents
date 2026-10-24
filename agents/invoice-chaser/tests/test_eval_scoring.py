"""Offline checks of the eval harness: scoring logic and plumbing (scripted model)."""

import json

import pytest

from evals import scoring
from tests.mock_llm import ScriptedLlm, call, text

AUTO = ["AUTO_APPLIED"]


@pytest.mark.parametrize("expected,outcome,passed,critical", [
    ({"invoice_ids": ["A"], "allowed_decisions": AUTO}, {"kind": "AUTO_APPLIED", "invoice_ids": ["A"]}, True, False),
    ({"invoice_ids": ["A"], "allowed_decisions": AUTO}, {"kind": "AUTO_APPLIED", "invoice_ids": ["B"]}, False, True),
    ({"invoice_ids": ["A"], "allowed_decisions": AUTO}, {"kind": "NEEDS_CONFIRMATION", "invoice_ids": ["A"]}, False, False),
    ({"invoice_ids": ["A"], "allowed_decisions": AUTO}, {"kind": "NONE", "invoice_ids": None}, False, False),
    ({"invoice_ids": ["B", "A"], "allowed_decisions": ["NEEDS_CONFIRMATION"]},
     {"kind": "NEEDS_CONFIRMATION", "invoice_ids": ["A", "B"]}, True, False),
    ({"invoice_ids": None, "allowed_decisions": []}, {"kind": "NONE", "invoice_ids": None}, True, False),
    ({"invoice_ids": None, "allowed_decisions": []}, {"kind": "NEEDS_CONFIRMATION", "invoice_ids": ["A"]}, False, False),
    ({"invoice_ids": None, "allowed_decisions": ["PENDING_OK"]}, {"kind": "NEEDS_CONFIRMATION", "invoice_ids": ["A"]}, True, False),
    ({"invoice_ids": None, "allowed_decisions": ["PENDING_OK"]}, {"kind": "AUTO_APPLIED", "invoice_ids": ["A"]}, False, True),
])
def test_score_matcher_case(expected, outcome, passed, critical):
    assert scoring.score_matcher_case(expected, outcome, None) == {"passed": passed, "critical": critical}


def test_runtime_error_fails_case():
    exp = {"invoice_ids": None, "allowed_decisions": []}
    assert scoring.score_matcher_case(exp, {"kind": "NONE", "invoice_ids": None}, "Timeout")["passed"] is False


def test_matcher_metrics():
    results = [
        {"id": "1", "expected": {"allowed_decisions": AUTO}, "outcome": {"kind": "AUTO_APPLIED"},
         "critical": False, "passed": True, "error": None},
        {"id": "2", "expected": {"allowed_decisions": AUTO}, "outcome": {"kind": "NEEDS_CONFIRMATION"},
         "critical": False, "passed": False, "error": None},
        {"id": "3", "expected": {"allowed_decisions": []}, "outcome": {"kind": "AUTO_APPLIED"},
         "critical": True, "passed": False, "error": None},
    ]
    m = scoring.matcher_metrics(results)
    assert (m["auto_apply_precision"], m["auto_apply_coverage"], m["critical_errors"]) == (0.5, 0.5, 1)
    assert m["failed_ids"] == ["2", "3"]


def test_rule_checks_language():
    item = {"invoice_id": "INV-1", "outstanding": "₹18,000", "recommended_tone": 1, "language": "hinglish"}
    good = {"tone_level": 1, "language": "hinglish", "subject": "Invoice INV-1",
            "body": "Namaste Rohit ji, invoice INV-1 ka ₹18,000 payment abhi pending hai. " * 3}
    assert scoring.rule_checks(good, item)["rules_passed"]
    english = {**good, "body": "Hi Rohit, invoice INV-1 for ₹18,000 is pending. Thanks. " * 3}
    assert not scoring.rule_checks(english, item)["rules"]["language_matches"]
    assert not scoring.rule_checks(good, {**item, "language": "en"})["rules"]["language_matches"]


def test_ungrounded_amounts_detected():
    from google.genai import types
    from google.adk.events import Event
    ev = Event(author="x", content=types.Content(role="user", parts=[types.Part.from_function_response(
        name="run_report", response={"content": [{"type": "text", "text": json.dumps({"total": "₹95,000"})}]})]))
    assert scoring.ungrounded_amounts("Matched ₹95,000 and ₹12,345", [ev]) == ["₹12,345"]
    assert scoring.ungrounded_amounts(None, [ev]) == []


def test_thresholds():
    ok_run = {"matcher": {"metrics": {"auto_apply_precision": 1.0, "pass_rate": 0.9, "critical_errors": 0}},
              "scenarios": {"metrics": {"passed": 2, "total": 2}}}
    assert scoring.all_thresholds_met({"runs": [ok_run]})
    bad = {**ok_run, "scenarios": {"metrics": {"passed": 1, "total": 2}}}
    assert not scoring.all_thresholds_met({"runs": [ok_run, bad]})


def test_matcher_suite_plumbing_with_scripted_model(monkeypatch):
    """Runs the real harness (fresh ledger, MCP subprocess, ADK runner) on two cases."""
    monkeypatch.setenv("INVOICE_CHASER_TODAY", "2026-10-24")
    monkeypatch.setenv("GOOGLE_API_KEY", "not-used")
    from evals import run_evals

    class SmartMock(ScriptedLlm):
        """Proposes INV-2026-001 for ACME lines, nothing otherwise."""
        def __init__(self):
            super().__init__(steps=[])

        async def generate_content_async(self, llm_request, stream=False):
            from tests.mock_llm import tool_responses
            seen = tool_responses(llm_request)
            if not seen:
                self.steps = [call("list_unmatched_payments")]
            elif seen[-1]["name"] == "list_unmatched_payments":
                payments = json.loads(seen[-1]["response"]["content"][0]["text"])["payments"]
                acme = [p for p in payments if "ACME" in p["narration_untrusted"]]
                self.steps = [call("propose_match", payment_id=acme[0]["payment_id"],
                                   invoice_ids=["INV-2026-001"], name_confidence=0.97,
                                   reason="ACME")] if acme else [text("unidentified")]
            else:
                self.steps = [text("done")]
            async for r in super().generate_content_async(llm_request, stream):
                yield r

    result = run_evals.suite_matcher(model=SmartMock(), only=["M01", "M14"])
    by_id = {c["id"]: c for c in result["cases"]}
    assert by_id["M01"]["outcome"]["kind"] == "AUTO_APPLIED" and by_id["M01"]["passed"]
    assert by_id["M14"]["outcome"]["kind"] == "NONE" and by_id["M14"]["passed"]
    assert result["metrics"]["critical_errors"] == 0


def test_daily_quota_detected_through_wrapped_errors():
    from evals.run_evals import DailyQuotaExhausted, _check_daily_quota
    inner = RuntimeError("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    try:
        try:
            raise inner
        except RuntimeError as e:
            raise ValueError("Dynamic node invoice_chaser failed") from e
    except ValueError as wrapped:
        with pytest.raises(DailyQuotaExhausted):
            _check_daily_quota(wrapped)
    _check_daily_quota(RuntimeError("429 GenerateRequestsPerMinute"))  # per-minute: retried, not fatal

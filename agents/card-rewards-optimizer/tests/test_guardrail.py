import pytest

from agent import (AgentError, as_of_numbers, make_tools, verify_numbers,
                   _generate_with_retry)
# fixtures `rates` and `sample_portfolio` come from the root conftest.py (fix 3A)


def test_verify_numbers_flags_any_number_not_allowed():
    allowed = {2026.0, 10.0, 24.0}
    assert verify_numbers("You'd get 99,999 from KrisFlyer", allowed) == [99999.0]


def test_verify_numbers_passes_when_only_as_of_date_present():
    allowed = {2026.0, 10.0, 24.0}
    assert verify_numbers("The strongest value is clear (rates as of 2026-10-24).", allowed) == []


def test_verify_numbers_catches_small_rate_fakes():      # no blanket small-number skip (F1)
    allowed = {0.75, 15000.0}
    assert verify_numbers("about 0.80 per point", allowed) == [0.80]
    assert verify_numbers("exactly 0.75 per point", allowed) == []


def test_as_of_numbers_from_date(rates):
    assert as_of_numbers(rates) == {2026.0, 10.0, 24.0}


# --- retry/clean-error layer, fully offline via a fake client ---
class _FakeModels:
    def __init__(self, behaviors):
        self._behaviors, self.calls = list(behaviors), 0

    def generate_content(self, model, contents):
        b = self._behaviors[self.calls]
        self.calls += 1
        if isinstance(b, Exception):
            raise b
        return type("R", (), {"text": b})()


class _FakeClient:
    def __init__(self, behaviors):
        self.models = _FakeModels(behaviors)


def test_retry_succeeds_on_second_attempt():
    client = _FakeClient([RuntimeError("429 rate limit exceeded"), "ok"])
    assert _generate_with_retry(client, "x", _sleep=lambda s: None) == "ok"
    assert client.models.calls == 2


def test_auth_error_is_not_retried():
    client = _FakeClient([RuntimeError("API key not valid")])
    with pytest.raises(AgentError, match="API key"):
        _generate_with_retry(client, "x", _sleep=lambda s: None)
    assert client.models.calls == 1


def test_non_retryable_error_becomes_agent_error():
    client = _FakeClient([RuntimeError("boom")])
    with pytest.raises(AgentError):
        _generate_with_retry(client, "x", _sleep=lambda s: None)
    assert client.models.calls == 1


def test_make_tools_log_and_numbers(sample_portfolio, rates):
    call_log, numbers = [], set()
    lookup, calc, expiry = make_tools(sample_portfolio, rates, call_log, numbers)
    out = calc("hdfc-infinia", "krisflyer", 20000)
    assert out["total_value_inr"] == 15000.0
    assert call_log == ["calculate_redemption_value"]
    assert 15000.0 in numbers and 20000.0 in numbers
    assert 0.75 in numbers               # per-point rate is tracked too (F1)


def test_check_expiry_returns_dict(sample_portfolio, rates):   # F8a
    call_log, numbers = [], set()
    _, _, expiry = make_tools(sample_portfolio, rates, call_log, numbers)
    out = expiry()
    assert isinstance(out, dict) and "alerts" in out
    assert call_log == ["check_expiry"]


def test_lookup_unknown_card_returns_error_not_exception(sample_portfolio, rates):
    call_log, numbers = [], set()
    lookup, _, _ = make_tools(sample_portfolio, rates, call_log, numbers)
    assert "error" in lookup("not-a-card")

from triage.models import Category, TestFailure
from triage.rules import classify, scan_log_for_infra


def test_rerun_passed_is_flaky():
    f = TestFailure(name="t", rerun_recorded=True, rerun_passed=True)
    assert classify(f, []).category == Category.FLAKY


def test_dns_in_log_is_infra():
    hits = scan_log_for_infra(["Could not resolve host: x"])
    f = TestFailure(name="t", message="Setup failed")
    assert classify(f, hits).category == Category.INFRA


def test_assertion_with_clean_history_is_regression():
    f = TestFailure(name="t", message="AssertionError: expected 1 but got 2")
    assert classify(f, [], {"t": ["pass"] * 5}).category == Category.REGRESSION


def test_assertion_without_history_defers_to_llm():
    f = TestFailure(name="t", message="AssertionError: expected 1 but got 2")
    assert classify(f, []) is None


def test_history_mixed_is_flaky():
    f = TestFailure(name="t", message="Timeout waiting for element")
    assert classify(f, [], {"t": ["pass", "fail", "pass"]}).category == Category.FLAKY

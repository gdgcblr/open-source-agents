from pathlib import Path

from flaky_test_triage.tools import (
    check_flakiness_history,
    classify_failure,
    combine_signals,
    parse_test_log,
)

LOGS = Path(__file__).parent.parent / "sample_logs"


def read(name):
    return (LOGS / name).read_text(encoding="utf-8")


def triage(name):
    log = read(name)
    parsed = parse_test_log(log)
    cls = classify_failure(log)
    hist = check_flakiness_history(parsed["test_name"])
    return parsed, cls, hist, combine_signals(cls, hist)


def test_selenium_timeout_is_flaky():
    parsed, cls, hist, final = triage("01_selenium_timeout.log")
    assert parsed["framework"] == "selenium"
    assert parsed["test_name"] == "CheckoutTest.testPaymentSpinnerDisappears"
    assert parsed["error_type"] == "TimeoutException"
    assert cls["category"] == "timing_synchronization"
    assert hist["history_verdict"] == "flaky"
    assert final["final_verdict"] == "flaky"


def test_api_assertion_with_failing_history_is_real_bug():
    _, cls, hist, final = triage("02_api_assertion.log")
    assert cls["category"] == "assertion_product_behavior"
    assert hist["history_verdict"] == "consistently_failing"
    assert final["final_verdict"] == "real_bug"


def test_connection_refused_is_environment_issue():
    _, cls, _, final = triage("03_env_connection.log")
    assert cls["category"] == "environment_infrastructure"
    assert final["final_verdict"] == "environment_issue"


def test_locator_change_is_test_issue():
    _, cls, _, final = triage("04_locator_changed.log")
    assert cls["category"] == "locator_ui_change"
    assert final["final_verdict"] == "test_issue"


def test_data_conflict_is_test_issue():
    parsed, cls, _, final = triage("05_pytest_data_conflict.log")
    assert parsed["framework"] == "pytest"
    assert cls["category"] == "test_data_state"
    assert final["final_verdict"] == "test_issue"


def test_unknown_log_needs_investigation():
    cls = classify_failure("something odd happened")
    assert cls["verdict"] == "unclear"
    assert combine_signals(cls, check_flakiness_history("nope"))["final_verdict"] == "needs_investigation"


def test_history_missing_test():
    assert check_flakiness_history("Does.notExist")["history_verdict"] == "no_history"

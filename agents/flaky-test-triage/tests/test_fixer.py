import pytest

from flaky_test_triage.fixer import fix_source, suggest_fix_diff


def test_sleep_replaced_with_explicit_wait():
    r = suggest_fix_diff("sample_src/CheckoutTest.java", "timing_synchronization")
    d = r["diff"]
    assert r["changed"] and r["rules_applied"] == ["sleep_to_wait"]
    assert "-        Thread.sleep(5000);" in d
    assert "+        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(10));" in d
    assert "ExpectedConditions.visibilityOfElementLocated(By.cssSelector(\".payment-success\"))" in d
    assert "+import java.time.Duration;" in d
    assert "NOT applied" in r["reminder"]


def test_brittle_xpath_replaced():
    r = suggest_fix_diff("sample_src/ProfileTest.java", "locator_ui_change")
    assert r["rules_applied"] == ["brittle_xpath"]
    assert "data-testid" in r["diff"] and "FIXME" in r["diff"]


def test_static_email_made_unique():
    r = suggest_fix_diff("sample_src/test_orders.py", "test_data_state")
    assert r["rules_applied"] == ["static_email"]
    assert "+import uuid" in r["diff"] and "uuid.uuid4().hex[:8]" in r["diff"]
    assert "REDACTED" not in r["diff"]


def test_no_category_tries_all_rules():
    assert suggest_fix_diff("sample_src/ProfileTest.java")["changed"] is True


def test_fix_is_idempotent():
    src = open("sample_src/CheckoutTest.java").read()
    once, a1, _ = fix_source(src, "CheckoutTest.java", ["sleep_to_wait"])
    twice, a2, _ = fix_source(once, "CheckoutTest.java", ["sleep_to_wait"])
    assert a1 and not a2 and once == twice


def test_environment_category_not_fixable_in_code():
    r = suggest_fix_diff("sample_src/CheckoutTest.java", "environment_infrastructure")
    assert r["changed"] is False and "not fixable" in r["notes"][0]


def test_sleep_without_find_gives_note():
    new, applied, notes = fix_source("class A {\n  void t() {\n    Thread.sleep(100);\n  }\n}", "A.java", ["sleep_to_wait"])
    assert not applied and notes and new.count("Thread.sleep") == 1


def test_file_is_never_modified():
    before = open("sample_src/CheckoutTest.java").read()
    suggest_fix_diff("sample_src/CheckoutTest.java")
    assert open("sample_src/CheckoutTest.java").read() == before


@pytest.mark.parametrize("bad", ["../../etc/passwd", ".env", "/etc/passwd", "README.md", "sample_src", "missing.py"])
def test_unsafe_or_unsupported_paths(bad):
    assert "error" in suggest_fix_diff(bad)

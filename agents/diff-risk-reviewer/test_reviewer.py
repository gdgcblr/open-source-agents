import pytest

from reviewer import main, mock_review, parse_diff, static_checks

SAMPLE = open("sample.diff", encoding="utf-8").read()


def titles(findings):
    return [f["title"] for f in findings]


def test_parse_diff_counts_files_and_lines():
    files = parse_diff(SAMPLE)
    assert set(files) == {"app/auth/login.py", "migrations/0007_add_last_login.sql"}
    assert files["migrations/0007_add_last_login.sql"]["removed"] == 0


def test_detects_hardcoded_credential_as_high():
    findings = static_checks(parse_diff(SAMPLE))
    assert any(f["severity"] == "high" and "secret" in f["title"].lower() for f in findings)


def test_detects_aws_key_built_at_runtime():
    fake_key = "AKIA" + "A" * 16  # built at runtime so no key-like string is committed
    diff = f"diff --git a/x.py b/x.py\n+++ b/x.py\n+k = '{fake_key}'\n"
    assert any("AWS" in t for t in titles(static_checks(parse_diff(diff))))


def test_flags_risky_files_missing_tests_and_debug():
    t = titles(static_checks(parse_diff(SAMPLE)))
    assert any("Sensitive file" in x for x in t)
    assert "Source changed without tests" in t
    assert "Debug/TODO leftovers" in t


def test_clean_diff_has_no_findings():
    diff = "diff --git a/notes.md b/notes.md\n+++ b/notes.md\n+hello\n"
    assert static_checks(parse_diff(diff)) == []


def test_mock_review_summary():
    assert "2 file(s)" in mock_review(parse_diff(SAMPLE))["summary"]


def test_fail_on_high_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        main(["sample.diff", "--mock", "--fail-on", "high"])
    assert exc.value.code == 1


def test_parse_json_response_handles_code_fences():
    from reviewer import parse_json_response

    assert parse_json_response('```json\n{"summary": "ok"}\n```') == {"summary": "ok"}
    assert parse_json_response('{"summary": "ok"}') == {"summary": "ok"}


def test_missing_xai_key_exits(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        main(["sample.diff", "--provider", "grok"])

"""
RepoLens — Unit Tests: Secret Redactor
"""
import pytest
from backend.scanner.redactor import redact, redact_evidence, contains_likely_secret


class TestRedact:

    def test_redacts_google_api_key(self):
        text = "Using key AIzaSyDSomeRealGoogleApiKey1234567890"
        result = redact(text)
        assert "AIzaSy" not in result
        assert "[REDACTED]" in result

    def test_redacts_github_pat(self):
        text = "Authorization: ghp_abcdefghijklmnopqrstuvwxyz123456789012"
        result = redact(text)
        assert "ghp_" not in result
        assert "[REDACTED]" in result

    def test_redacts_aws_access_key(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result

    def test_redacts_generic_api_key_pattern(self):
        text = "api_key=supersecretvalue12345678901234"
        result = redact(text)
        assert "supersecretvalue12345678901234" not in result

    def test_leaves_safe_text_unchanged(self):
        safe = "The quick brown fox jumps over the lazy dog."
        assert redact(safe) == safe

    def test_empty_string(self):
        assert redact("") == ""

    def test_redacts_basic_auth_url(self):
        text = "mongodb://admin:password123@localhost:27017/db"
        result = redact(text)
        assert "password123" not in result

    def test_multiple_secrets_all_redacted(self):
        text = (
            "key=AIzaSyDSomeRealGoogleApiKey1234567890 "
            "and also AKIAIOSFODNN7EXAMPLE"
        )
        result = redact(text)
        assert "AIzaSy" not in result
        assert "AKIA" not in result


class TestRedactEvidence:

    def test_truncation(self):
        long_text = "a" * 5000
        result = redact_evidence(long_text, max_bytes=100)
        assert result is not None
        assert len(result.encode("utf-8")) <= 200  # truncated + "[TRUNCATED]"
        assert "[TRUNCATED]" in result

    def test_none_returns_none(self):
        assert redact_evidence(None) is None

    def test_within_limit_not_truncated(self):
        short = "hello world"
        result = redact_evidence(short, max_bytes=100)
        assert result == "hello world"


class TestContainsLikelySecret:

    def test_detects_github_pat(self):
        assert contains_likely_secret("token=ghp_abcdefghijklmnopqrstuvwxyz123456789012")

    def test_safe_text_not_flagged(self):
        assert not contains_likely_secret("This is a normal sentence.")

    def test_detects_aws_key(self):
        assert contains_likely_secret("AKIAIOSFODNN7EXAMPLE")

"""Tests for the log sanitizer module."""

import pytest

from incident_analyzer.sanitizer import (
    sanitize_log,
    sanitize_file_path,
    validate_no_secrets,
)


# ── API Key & Token Redaction ──────────────────────────────────────────


def test_redacts_generic_api_key():
    """Test that generic API key patterns are redacted."""
    log = 'api_key = "sk-abc123def456ghi789jkl012mno345"'
    sanitized, report = sanitize_log(log)
    assert "sk-abc123def456ghi789jkl012mno345" not in sanitized
    assert "<REDACTED_API_KEY>" in sanitized
    assert report.was_modified


def test_redacts_api_secret():
    """Test that API secret patterns are redacted."""
    log = "API_SECRET: superSecretValue12345678901234"
    sanitized, report = sanitize_log(log)
    assert "superSecretValue12345678901234" not in sanitized
    assert report.was_modified


def test_redacts_bearer_token():
    """Test that bearer/authorization tokens are redacted."""
    log = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'
    sanitized, report = sanitize_log(log)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert report.was_modified


def test_redacts_aws_access_key():
    """Test that AWS access key IDs are redacted."""
    log = "Using key: AKIAIOSFODNN7EXAMPLE"
    sanitized, report = sanitize_log(log)
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "<REDACTED_AWS_KEY>" in sanitized
    assert report.was_modified


# ── Password Redaction ─────────────────────────────────────────────────


def test_redacts_password():
    """Test that password patterns are redacted."""
    log = 'password = "my_super_secret_pwd_123"'
    sanitized, report = sanitize_log(log)
    assert "my_super_secret_pwd_123" not in sanitized
    assert "<REDACTED_PASSWORD>" in sanitized
    assert report.was_modified


def test_redacts_password_colon_format():
    """Test password redaction with colon separator."""
    log = "DB_PASSWORD: hunter2_complex"
    sanitized, report = sanitize_log(log)
    assert "hunter2_complex" not in sanitized
    assert report.was_modified


# ── Database URI Redaction ─────────────────────────────────────────────


def test_redacts_postgres_uri():
    """Test that PostgreSQL connection strings are redacted."""
    log = "Connecting to: postgresql://admin:secret@db.example.com:5432/mydb"
    sanitized, report = sanitize_log(log)
    assert "admin:secret@db.example.com" not in sanitized
    assert "<REDACTED_DB_URI>" in sanitized
    assert report.was_modified


def test_redacts_mongodb_uri():
    """Test that MongoDB connection strings are redacted."""
    log = "mongodb://user:pass@cluster.mongodb.net/test"
    sanitized, report = sanitize_log(log)
    assert "user:pass" not in sanitized
    assert report.was_modified


# ── Email & IP Redaction ───────────────────────────────────────────────


def test_redacts_email_addresses():
    """Test that email addresses are redacted."""
    log = "Error reported by user developer@company.com at 2024-01-01"
    sanitized, report = sanitize_log(log)
    assert "developer@company.com" not in sanitized
    assert "<REDACTED_EMAIL>" in sanitized
    assert report.was_modified


def test_redacts_ipv4_addresses():
    """Test that IPv4 addresses are redacted."""
    log = "Connection refused from 192.168.1.100 to 10.0.0.5"
    sanitized, report = sanitize_log(log)
    assert "192.168.1.100" not in sanitized
    assert "10.0.0.5" not in sanitized
    assert report.was_modified


# ── JWT Token Redaction ────────────────────────────────────────────────


def test_redacts_jwt_tokens():
    """Test that JWT tokens are redacted."""
    log = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    sanitized, report = sanitize_log(log)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert "<REDACTED_JWT>" in sanitized
    assert report.was_modified


# ── Private Key Redaction ──────────────────────────────────────────────


def test_redacts_private_key_block():
    """Test that PEM private key blocks are redacted."""
    log = """Loading credentials:
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/yGJ0nM3bMCZ
-----END RSA PRIVATE KEY-----
Done."""
    sanitized, report = sanitize_log(log)
    assert "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn" not in sanitized
    assert "<REDACTED_PRIVATE_KEY_BLOCK>" in sanitized
    assert report.was_modified


# ── Hex Token Redaction ────────────────────────────────────────────────


def test_redacts_high_entropy_hex():
    """Test that long hex strings are redacted."""
    log = "Session ID: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    sanitized, report = sanitize_log(log)
    assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" not in sanitized
    assert "<REDACTED_HEX_TOKEN>" in sanitized
    assert report.was_modified


# ── Home Directory Path Redaction ──────────────────────────────────────


def test_redacts_home_directory_paths():
    """Test that user home directory paths are sanitized."""
    log = 'File "/Users/johndoe/projects/app/main.py", line 42, in main'
    sanitized, report = sanitize_log(log)
    assert "johndoe" not in sanitized
    assert "<REDACTED_USER>" in sanitized
    assert report.was_modified


def test_redacts_linux_home_paths():
    """Test redaction of Linux home directory paths."""
    log = 'File "/home/developer/src/app.py", line 10, in run'
    sanitized, report = sanitize_log(log)
    assert "developer" not in sanitized
    assert report.was_modified


# ── No False Positives ─────────────────────────────────────────────────


def test_preserves_normal_stack_trace():
    """Test that normal traceback structure is preserved."""
    log = """Traceback (most recent call last):
  File "app.py", line 42, in process_data
    result = transform(data)
  File "utils.py", line 15, in transform
    return data.split(",")
AttributeError: 'NoneType' object has no attribute 'split'"""
    sanitized, report = sanitize_log(log)
    assert "Traceback (most recent call last):" in sanitized
    assert "AttributeError" in sanitized
    assert "process_data" in sanitized
    assert "transform" in sanitized


def test_preserves_error_messages():
    """Test that error type and message are preserved."""
    log = "ValueError: invalid literal for int() with base 10: 'abc'"
    sanitized, _ = sanitize_log(log)
    assert "ValueError" in sanitized
    assert "invalid literal" in sanitized


# ── sanitize_file_path tests ──────────────────────────────────────────


def test_sanitize_file_path_mac():
    """Test file path sanitization for macOS paths."""
    path = "/Users/johndoe/projects/myapp/src/main.py"
    result = sanitize_file_path(path)
    assert "johndoe" not in result
    assert "<USER>" in result
    assert "main.py" in result


def test_sanitize_file_path_linux():
    """Test file path sanitization for Linux paths."""
    path = "/home/developer/src/app.py"
    result = sanitize_file_path(path)
    assert "developer" not in result
    assert "<USER>" in result


def test_sanitize_file_path_no_user():
    """Test that paths without user directories are unchanged."""
    path = "/var/log/app.log"
    result = sanitize_file_path(path)
    assert result == path


# ── validate_no_secrets tests ─────────────────────────────────────────


def test_validate_no_secrets_detects_api_key():
    """Test that validate_no_secrets catches API keys."""
    text = 'api_key = "sk-1234567890abcdefghijklmnop"'
    warnings = validate_no_secrets(text)
    assert len(warnings) > 0
    assert any("API Key" in w for w in warnings)


def test_validate_no_secrets_clean_text():
    """Test that clean text produces no warnings."""
    text = "Normal log output: Application started successfully"
    warnings = validate_no_secrets(text)
    assert len(warnings) == 0


# ── SanitizationReport tests ─────────────────────────────────────────


def test_report_was_modified_true():
    """Test that was_modified is True when redactions occurred."""
    log = "api_key = sk-12345678901234567890"
    _, report = sanitize_log(log)
    assert report.was_modified is True
    assert len(report.redactions) > 0


def test_report_was_modified_false():
    """Test that was_modified is False for clean input."""
    log = "Normal application log line with no secrets"
    _, report = sanitize_log(log)
    assert report.was_modified is False
    assert len(report.redactions) == 0


def test_report_lengths():
    """Test that original and sanitized lengths are tracked."""
    log = "api_key = sk-12345678901234567890"
    _, report = sanitize_log(log)
    assert report.original_length == len(log)
    assert report.sanitized_length > 0

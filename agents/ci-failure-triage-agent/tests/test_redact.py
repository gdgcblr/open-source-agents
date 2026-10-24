from triage.privacy import redact

# Secrets are assembled at runtime so no realistic token literal is ever committed.
GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
AWS = "AKIA" + "IOSFODNN7EXAMPLE"


def test_github_token():
    assert GH not in redact(f"token {GH} used")


def test_aws_key():
    assert AWS not in redact(f"key={AWS}")


def test_bearer_and_email_and_ip():
    out = redact("Authorization: Bearer abcdefghij123456 from bob@corp.io at 192.168.1.20")
    assert "abcdefghij123456" not in out and "bob@corp.io" not in out and "192.168.1.20" not in out


def test_secret_assignment():
    assert "hunter2hunter2" not in redact("DB_PASSWORD=hunter2hunter2")


def test_url_credentials():
    assert "s3cr3t" not in redact("https://user:s3cr3t@host.example/path")


def test_clean_text_unchanged():
    assert redact("AssertionError: expected 90 but got 100") == "AssertionError: expected 90 but got 100"

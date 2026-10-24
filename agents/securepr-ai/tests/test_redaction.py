from securepr.redaction import Redactor


def test_redactor_scrubs_aws_keys():
    redactor = Redactor()
    raw = "aws_key = 'AKIA1234567890ABCDEF'"
    cleaned, count = redactor.redact_text(raw)
    assert count >= 1
    assert "AKIA1234567890ABCDEF" not in cleaned
    assert "[REDACTED_AWS_KEY]" in cleaned


def test_redactor_scrubs_jwt_tokens():
    redactor = Redactor()
    header = "eyJ" + "hbGciOiJIUzI1NiJ9"
    payload = "eyJ" + "zdWIiOiJ1c2VyIn0"
    jwt = ".".join((header, payload, "signature123456789"))
    cleaned, count = redactor.redact_text("Authorization: " + jwt)
    assert count >= 1
    assert jwt not in cleaned
    assert "[REDACTED_JWT_TOKEN]" in cleaned

def test_redactor_scrubs_database_url():
    redactor = Redactor()
    password = "example" + "-password"
    database_url = "postgres://demo:" + password + "@db.internal:5432/production"
    cleaned, count = redactor.redact_text("DATABASE_URL=" + database_url)
    assert count >= 1
    assert password not in cleaned
    assert "[REDACTED_PASS]" in cleaned

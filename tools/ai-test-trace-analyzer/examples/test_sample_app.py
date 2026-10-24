import pytest

from sample_app import create_user, normalize_email


def test_normalize_email():
    assert normalize_email("  USER@Example.com ") == "user@example.com"


def test_create_user():
    user = create_user("USER@example.com")
    assert user["id"] == 123
    assert user["email"] == "user@example.com"


def test_invalid_email_raises():
    with pytest.raises(ValueError, match="email must contain @"):
        create_user("not-an-email")

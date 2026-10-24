"""Local email/password accounts. Passwords are stored as a slow hash."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ITERATIONS = 600_000


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    cleaned = normalize_email(email)
    return 3 <= len(cleaned) <= 254 and EMAIL_RE.fullmatch(cleaned) is not None


def valid_password(password: str) -> bool:
    return 8 <= len(password) <= 200


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), ITERATIONS
    )
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except (AttributeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        int(iterations),
    )
    return hmac.compare_digest(check.hex(), digest)

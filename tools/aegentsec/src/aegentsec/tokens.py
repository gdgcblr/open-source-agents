import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from aegentsec.config import Settings


def _b64int(value: int) -> str:
    data = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class TokenService:
    def __init__(self, settings: Settings):
        self.settings = settings
        path = Path(settings.iam_private_key_path)
        self.private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(self.private_key, rsa.RSAPrivateKey):
            raise TypeError("IAM signing key must be RSA")
        self.public_key = self.private_key.public_key()

    def issue(self, agent: dict, scopes: list[str], audience: str) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iss": self.settings.iam_issuer,
                "sub": agent["agent_id"],
                "aud": audience,
                "client_id": agent["client_id"],
                "enterprise_id": agent["enterprise_id"],
                "scope": " ".join(scopes),
                "iat": now,
                "exp": now + timedelta(minutes=self.settings.jwt_expiration_minutes),
                "jti": uuid4().hex,
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.settings.iam_key_id},
        )

    def verify(self, token: str, audience: str) -> dict:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or header.get("kid") != self.settings.iam_key_id:
            raise jwt.InvalidTokenError("Unexpected signing key or algorithm")
        return jwt.decode(
            token,
            self.public_key,
            algorithms=["RS256"],
            issuer=self.settings.iam_issuer,
            audience=audience,
            options={
                "require": ["iss", "sub", "aud", "client_id", "enterprise_id", "iat", "exp", "jti"]
            },
        )

    def jwks(self) -> dict:
        numbers = self.public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self.settings.iam_key_id,
                    "n": _b64int(numbers.n),
                    "e": _b64int(numbers.e),
                }
            ]
        }

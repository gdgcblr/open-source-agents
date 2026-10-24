"""Generate a persistent development RSA signing key. Run from the project directory."""

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    path = Path(os.getenv("IAM_PRIVATE_KEY_PATH", "./keys/private.pem"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing signing key: {path}")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    print(f"Created {path}")


if __name__ == "__main__":
    main()

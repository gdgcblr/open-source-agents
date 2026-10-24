"""Signing and trust levels for stored memory.

Idea borrowed from adk-memshield (aalishan001/adk-memshield, Apache-2.0): memory must be
bound to an identity and a trust level, and low-trust writers must not be able to plant
content that higher-trust readers rely on. No code is copied; this is a SQLite/HMAC take.

Threat: a repo can ship its own `.rce-sentinel/sentinel.db` with pre-baked "safe" verdicts.
Every cached verdict and fact is therefore HMAC-signed with a per-machine key kept outside
the repo, and rows with a missing or wrong signature are ignored.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

UNVERIFIED = 0  # rules only, unconfirmed intel, or a single model with no second opinion
SINGLE = 1      # one model, no cross-family check (only ever stored for "vulnerable")
VERIFIED = 2    # a model from a different family agreed

SEP = "\x1f"


def default_key_path() -> Path:
    env = os.environ.get("RCE_SENTINEL_KEY_FILE")
    return Path(env) if env else Path.home() / ".config" / "rce-sentinel" / "key"


class Signer:
    """HMAC-SHA256 over an ordered list of fields, with a 32-byte per-machine key."""

    def __init__(self, key: bytes):
        if len(key) < 16:
            raise ValueError("signing key too short")
        self._key = key

    @classmethod
    def load(cls, path: Path | None = None) -> Signer:
        path = path or default_key_path()
        if path.exists():
            return cls(bytes.fromhex(path.read_text().strip()))
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(key.hex())
        return cls(key)

    def sign(self, *fields: object) -> str:
        msg = SEP.join(str(f) for f in fields).encode("utf-8", "replace")
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def verify(self, sig: str | None, *fields: object) -> bool:
        return bool(sig) and hmac.compare_digest(sig, self.sign(*fields))  # type: ignore[arg-type]


def repo_id(root: Path) -> str:
    """Stable id for a repository, so facts from one repo never apply to another."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]

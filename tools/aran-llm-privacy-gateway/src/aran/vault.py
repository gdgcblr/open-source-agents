"""Local token vault: maps <TYPE_n> tokens to real values. Never leaves the machine.

One vault file per session under $ARAN_HOME/vault (default ~/.aran), readable only by the
current user. The same real value always gets the same token within a session, so the
cloud model can still tell that the PAN on the PAN card and the bank statement match.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def aran_home() -> Path:
    home = Path(os.environ.get("ARAN_HOME", Path.home() / ".aran"))
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    return home


def _vault_dir() -> Path:
    d = aran_home() / "vault"
    d.mkdir(mode=0o700, exist_ok=True)
    return d


def new_session_id() -> str:
    return "s_" + secrets.token_hex(6)


_SESSION_RE = re.compile(r"^s_[0-9a-f]{12}$")


@contextmanager
def open_session(session_id: str | None = None) -> Iterator["Vault"]:
    """Load, modify and save a session's vault under an exclusive lock.

    Agents call tools in parallel, so several redactions can hit one session at once.
    Without the lock, the last save wins: tokens are lost, two values can share a token,
    and the file can be corrupted.
    """
    sid = session_id or new_session_id()
    if not _SESSION_RE.match(sid):
        raise ValueError(f"Invalid session id: {sid!r}")
    fd = os.open(_vault_dir() / f"{sid}.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        vault = Vault(sid)
        yield vault
        vault.save()
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _normalise(pii_type: str, value: str) -> str:
    if pii_type in {"PERSON", "ADDRESS", "ORG"}:
        return " ".join(value.casefold().split())
    return re.sub(r"[\s-]", "", value).upper()


class Vault:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or new_session_id()
        if not _SESSION_RE.match(self.session_id):
            raise ValueError(f"Invalid session id: {self.session_id!r}")
        self.path = _vault_dir() / f"{self.session_id}.json"
        self.tokens: dict[str, dict[str, str]] = {}  # token -> {"type", "value"}
        self._index: dict[str, str] = {}  # type:normalised value -> token
        self._counters: dict[str, int] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        data = json.loads(self.path.read_text())
        self.tokens = data["tokens"]
        self._counters = data["counters"]
        for token, entry in self.tokens.items():
            self._index[f"{entry['type']}:{_normalise(entry['type'], entry['value'])}"] = token

    def token_for(self, pii_type: str, value: str) -> str:
        key = f"{pii_type}:{_normalise(pii_type, value)}"
        if key not in self._index:
            n = self._counters.get(pii_type, 0) + 1
            self._counters[pii_type] = n
            token = f"<{pii_type}_{n}>"
            self._index[key] = token
            self.tokens[token] = {"type": pii_type, "value": value}
        return self._index[key]

    def save(self) -> None:
        payload = json.dumps({"tokens": self.tokens, "counters": self._counters}, ensure_ascii=False)
        # Write-then-rename so a concurrent reader (e.g. restore) never sees a half-written file.
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        os.replace(tmp, self.path)

    # Accept the canonical <PERSON_1> plus forms models sometimes emit: [PERSON_1], PERSON_1.
    _TOKEN_RE = re.compile(r"[<\[]?\b([A-Z]+(?:_[A-Z]+)*_\d+)\b[>\]]?")

    def restore(self, text: str) -> str:
        def sub(m: re.Match[str]) -> str:
            entry = self.tokens.get(f"<{m.group(1)}>")
            return entry["value"] if entry else m.group(0)

        return self._TOKEN_RE.sub(sub, text)

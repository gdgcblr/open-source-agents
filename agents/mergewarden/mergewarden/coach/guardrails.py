"""Deterministic guardrails that run before (and around) any LLM call.

Nothing here talks to a network or a model: same input, same decision.
The secret and injection detectors are the gatekeeper's own, so the coach
holds students to exactly the bar their PR will later be judged by.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from ..checks import injection
from ..checks.secrets import GENERIC, PLACEHOLDER, VENDOR_PATTERNS, _entropy
from . import config

# --- identity ---------------------------------------------------------------


def hash_user(raw_id: str, salt: str | None = None) -> str:
    """sha256(phone + salt). The raw phone number is never stored anywhere."""
    norm = re.sub(r"^whatsapp:", "", raw_id.strip())
    return hashlib.sha256((norm + (config.SALT if salt is None else salt)).encode()).hexdigest()


# --- secrets ----------------------------------------------------------------

# Things a student might paste that are not API keys but must never be shared.
CREDENTIAL_TALK = re.compile(
    r"(?i)\b(?:passw(?:or)?d|pwd|otp|one[- ]time (?:code|password)|pin|2fa code|verification code|token|api[ _-]?key)"
    r"\b\s*(?:is|=|:|-)?\s*[\"']?(\S{4,})"
)


def find_secret(text: str) -> str | None:
    """Return a short label of the credential found in `text`, or None."""
    for name, pat in VENDOR_PATTERNS.items():
        if re.search(pat, text):
            return name
    m = GENERIC.search(text)
    if m and not PLACEHOLDER.search(m.group(2)) and _entropy(m.group(2)) > 3.5:
        return "a secret value"
    m = CREDENTIAL_TALK.search(text)
    if m and not PLACEHOLDER.search(m.group(1)) and (any(c.isdigit() for c in m.group(1)) or len(m.group(1)) >= 8):
        return "a password or one-time code"
    return None


# --- prompt injection -------------------------------------------------------

EXTRA_INJECTION = [
    r"\bignore\s+(?:all\s+|your\s+)?(?:rules|instructions|guidelines)",
    r"\b(?:award|give|grant|add)\s+(?:me\s+)?\d+\s+points\b",
    r"\bpretend\s+(?:to\s+be|you\s+are)\b",
    r"\breveal\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)",
]


def injection_flags(text: str) -> list[str]:
    """Reuse the gatekeeper scanner, plus a few coach-specific patterns."""
    hits = [what for _, what in injection.scan(text)]
    for pat in EXTRA_INJECTION:
        m = re.search(pat, text, re.I)
        if m:
            hits.append(f"instruction aimed at the coach: \"{m.group(0)[:60]}\"")
    return hits


def untrusted(text: str, source: str) -> str:
    """Wrap untrusted content so the model can tell data from instructions."""
    clean = text.replace("</untrusted>", "&lt;/untrusted&gt;")
    return f'<untrusted source="{source}">\n{clean}\n</untrusted>'


# --- privacy ----------------------------------------------------------------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{7,}\d(?![\w/])")


def redact(text: str) -> str:
    """Strip emails and phone numbers before text is stored or sent to the model."""
    def phone(m: re.Match) -> str:  # 10+ digits: not a date, version or issue number
        return "[phone]" if sum(c.isdigit() for c in m.group(0)) >= 10 else m.group(0)

    return PHONE.sub(phone, EMAIL.sub("[email]", text))


# --- abuse ------------------------------------------------------------------


class RateLimiter:
    """Sliding-window limit per user (in memory; a restart forgives everyone)."""

    def __init__(self, limit: int | None = None, window_s: int | None = None):
        self.limit = limit or config.RATE_LIMIT_MSGS
        self.window = window_s or config.RATE_LIMIT_WINDOW_S
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def audio_problem(audio: bytes, mime: str | None) -> str | None:
    """Reject oversized or overlong voice notes before they reach the model."""
    if len(audio) > config.MAX_AUDIO_BYTES:
        return f"Voice notes can be up to {config.MAX_AUDIO_BYTES // (1024 * 1024)} MB."
    if not (mime or "").startswith("audio/"):
        return "I can only listen to audio voice notes."
    # Compressed voice notes (ogg/opus, webm, mp4/aac) are well under 128 kbit/s,
    # so this upper-bound estimate never rejects a legitimate 2-minute note.
    if "wav" not in mime and len(audio) / 16_000 > config.MAX_AUDIO_SECONDS:
        return f"Voice notes can be up to {config.MAX_AUDIO_SECONDS // 60} minutes."
    return None


# --- sandboxed file writes --------------------------------------------------

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
ALLOWED_EXT = {".md", ".txt", ".py", ".yaml", ".yml", ".json", ".toml", ".patch", ".diff", ".js", ".ts"}


class SandboxError(ValueError):
    pass


def sandbox_path(base: Path, *parts: str) -> Path:
    """Resolve `parts` under `base`, refusing anything that escapes it.

    Each part must be a plain file/folder name (no slashes, no '..', no
    leading dot), and the resolved path must still sit inside `base`.
    """
    base = base.resolve()
    for p in parts:
        if not SAFE_NAME.match(p or "") or ".." in p:
            raise SandboxError(f"unsafe path component: {p!r}")
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise SandboxError("path escapes the sandbox")
    return target


def safe_draft_name(name: str) -> str:
    name = Path(name or "").name  # drop any directories the model invents
    if not SAFE_NAME.match(name) or Path(name).suffix.lower() not in ALLOWED_EXT:
        raise SandboxError(f"draft file name not allowed: {name!r}")
    return name


def slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-")
    return s or "issue"

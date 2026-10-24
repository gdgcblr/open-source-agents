"""Masking, handles, and scrubbing of known secret values."""

from __future__ import annotations

import base64
import dataclasses
import json
import re
import threading
import urllib.parse
from typing import Any

HANDLE_PREFIX = "keyguard://"
NAME_RE = r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}"
HANDLE_RE = re.compile(r"keyguard://(" + NAME_RE + r")")
_NAME_FULL = re.compile(r"^" + NAME_RE + r"$")


def valid_name(name: str) -> bool:
    return bool(_NAME_FULL.match(name or ""))


def handle(name: str) -> str:
    return HANDLE_PREFIX + name


# Documented, non-secret prefixes of common token formats (OpenAI/Anthropic, Stripe, GitHub,
# GitLab, Slack, AWS, Google, npm, PyPI, Hugging Face).
_PUBLIC_PREFIX = re.compile(r"^(?:sk-ant-|sk-proj-|sk-|sk_live_|sk_test_|pk_live_|pk_test_|rk_live_|rk_test_|"
                            r"whsec_|github_pat_|gh[pousr]_|glpat-|xox[abprs]-|xapp-|AKIA|ASIA|AIza|ya29\.|"
                            r"npm_|pypi-|hf_)")


def mask(value: str) -> str:
    """Masked preview. Only a documented public token prefix (sk-, ghp_, xoxb-, AKIA...) of a
    16+ char value is shown; no character of the secret part is ever revealed."""
    n = len(value)
    m = _PUBLIC_PREFIX.match(value) if n >= 16 else None
    return f"{m.group(0) if m else ''}****[{n} chars]"


def to_jsonable(obj: Any, _depth: int = 0) -> tuple[Any, bool]:
    """Convert a tool result to plain JSON data. Returns (data, converted).

    `converted` is True if anything was not already JSON-native (dataclass, set, bytes,
    pydantic model, custom object...). Such values are serialized later by ADK/genai, after
    keyguard has run, so they are converted (and then scrubbed) here instead.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj, False
    if _depth > 50:
        return str(obj), True
    if isinstance(obj, SecretValue):
        return repr(obj), True
    if isinstance(obj, dict):
        out, conv = {}, False
        for k, v in obj.items():
            v2, c = to_jsonable(v, _depth + 1)
            out[k if isinstance(k, str) else str(k)] = v2
            conv = conv or c or not isinstance(k, str)
        return out, conv
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [to_jsonable(v, _depth + 1) for v in obj]
        return [v for v, _ in items], not isinstance(obj, list) or any(c for _, c in items)
    if isinstance(obj, (bytes, bytearray, memoryview)):
        raw = bytes(obj)
        try:
            return raw.decode("utf-8"), True
        except UnicodeDecodeError:
            return base64.b64encode(raw).decode("ascii"), True
    if hasattr(obj, "model_dump"):
        try:
            return to_jsonable(obj.model_dump(mode="json"), _depth + 1)[0], True
        except Exception:
            pass
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        try:
            return to_jsonable(dataclasses.asdict(obj), _depth + 1)[0], True
        except Exception:
            pass
    return str(obj), True


class SecretValue:
    """Wraps a plaintext secret; str/repr/format are masked. Call reveal() deliberately."""

    __slots__ = ("_name", "_value")

    def __init__(self, name: str, value: str):
        self._name = name
        self._value = value

    @property
    def name(self) -> str:
        return self._name

    def reveal(self) -> str:
        return self._value

    def masked(self) -> str:
        return mask(self._value)

    def __repr__(self) -> str:
        return f"SecretValue({self._name!r}, {self.masked()!r})"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __reduce__(self):
        raise TypeError("SecretValue cannot be pickled")


def _variants(value: str) -> set[str]:
    """Encodings in which a secret commonly re-appears in tool output or logs."""
    raw = value.encode("utf-8")
    out = {value, urllib.parse.quote(value, safe=""), urllib.parse.quote_plus(value),
           json.dumps(value)[1:-1], raw.hex(), raw.hex().upper()}
    for enc in (base64.b64encode, base64.urlsafe_b64encode):
        full = enc(raw).decode("ascii")
        out.add(full.rstrip("="))
        out.add(full[: (len(raw) // 3) * 4])  # followed by other bytes (e.g. "token:extra")
        for k in (1, 2):  # preceded by k other bytes, e.g. Basic auth "user:password"
            shifted = enc(bytes(k) + raw).decode("ascii")
            out.add(shifted[4: ((k + len(raw)) // 3) * 4])
    return out


def string_leaves(obj: Any) -> list[str]:
    """Every string (and number) inside plain JSON data, keys included."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, (int, float)):
        return [str(obj)]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in (*string_leaves(k), *string_leaves(v))]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in string_leaves(v)]
    return [str(obj)]


class Redactor:
    """Replaces any known secret value (raw, URL/JSON-escaped, hex, base64) with a placeholder.

    A safety net, not a guarantee: values shorter than MIN_LEN, case changes, reversed or
    split output are not caught. Raw values shorter than WORD_LEN only match as a whole
    word (not inside a longer run of letters/digits), so 'admin' does not match
    'administrator'. Scrubbing and guess detection use the same matching rule.
    """

    MIN_LEN = 4
    MIN_ENCODED = 8  # shorter encoded fragments would cause false positives
    WORD_LEN = 12

    def __init__(self) -> None:
        self._known: dict[str, str] = {}
        self._exposed: set[str] = set()  # values the model was given (e.g. store_secret(value=...))
        self._word: dict[str, re.Pattern] = {}  # short raw values: whole-word matching
        self._lock = threading.Lock()

    def add(self, name: str, value: str, *, exposed: bool = False) -> None:
        if len(value) < self.MIN_LEN:
            return
        with self._lock:
            for v in _variants(value):
                if v == value or len(v) >= self.MIN_ENCODED:
                    self._known[v] = name
                    if exposed:
                        self._exposed.add(v)
            if len(value) < self.WORD_LEN:
                self._word[value] = re.compile(r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])")

    def clear(self) -> None:
        with self._lock:
            self._known.clear()
            self._exposed.clear()
            self._word.clear()

    def __bool__(self) -> bool:
        return bool(self._known)

    def _in(self, value: str, text: str) -> bool:
        pattern = self._word.get(value)
        return bool(pattern.search(text)) if pattern is not None else value in text

    def scrub_text(self, text: str) -> str:
        with self._lock:
            items = sorted(self._known.items(), key=lambda kv: -len(kv[0]))
        for value, name in items:
            if value in text:
                placeholder = f"[REDACTED:{handle(name)}]"
                pattern = self._word.get(value)
                text = pattern.sub(placeholder, text) if pattern is not None else text.replace(value, placeholder)
        return text

    def scrub(self, obj: Any) -> Any:
        """Scrub known values from any object. Other types (bytes, sets, dataclasses, custom
        objects) are returned unchanged if clean, else as their scrubbed JSON form (see to_jsonable)."""
        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        if isinstance(obj, str):
            return self.scrub_text(obj)
        if isinstance(obj, dict):
            return {self.scrub(k): self.scrub(v) for k, v in obj.items()}
        if type(obj) in (list, tuple):
            return type(obj)(self.scrub(v) for v in obj)
        data, _ = to_jsonable(obj)
        clean = self.scrub(data)
        return obj if clean == data and not isinstance(obj, SecretValue) else clean

    def contains(self, obj: Any, *, guesses_only: bool = False) -> bool:
        """True if any known value (or encoding of it) appears anywhere in obj.

        guesses_only=True ignores values the model was given itself, so what remains in
        model-authored content can only be a guess.
        """
        leaves = string_leaves(to_jsonable(obj)[0])
        with self._lock:
            values = [v for v in self._known if not (guesses_only and v in self._exposed)]
        return any(self._in(v, s) for s in leaves for v in values)

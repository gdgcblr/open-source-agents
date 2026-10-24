"""The single choke point for sensitive data. Everything that leaves the process boundary
(LLM prompt, tool output, report) must pass through `redact`."""
import hashlib
import hmac
import os
from collections import Counter
from typing import Iterable, Optional

from .detectors import DETECTORS, Detector, custom_detector

# Per-process salt: pseudonyms are stable inside one run but cannot be linked across runs
# or reversed. No mapping table exists, so no PII is ever stored.
_SALT = os.urandom(16)


def _marker(det: Detector, value: str) -> str:
    if det.secret:
        return f"[REDACTED:{det.kind}]"
    h = hmac.new(_SALT, f"{det.kind}:{value.lower()}".encode(), hashlib.sha256).hexdigest()[:6]
    return f"[{det.kind}:{h}]"


def _apply(det: Detector, text: str, stats: Optional[Counter]) -> str:
    def repl(m):
        value = m.group(det.group)
        if value is None or value.startswith("[") or (det.validate and not det.validate(value)):
            return m.group(0)
        if stats is not None:
            stats[det.kind] += 1
        s, e = m.span(det.group)
        base = m.start()
        whole = m.group(0)
        return whole[: s - base] + _marker(det, value) + whole[e - base :]

    return det.pattern.sub(repl, text)


def redact(text: str, stats: Optional[Counter] = None) -> str:
    """Return `text` with secrets and PII replaced. Idempotent. Optionally counts findings by kind."""
    if not text:
        return text
    for det in DETECTORS:
        text = _apply(det, text, stats)
    extra = custom_detector()
    if extra:
        text = _apply(extra, text, stats)
    return text


def scan(texts: Iterable[str]) -> dict[str, int]:
    """Count what would be redacted (kinds and numbers only, never values)."""
    stats: Counter = Counter()
    for t in texts:
        redact(t, stats)
    return dict(stats)

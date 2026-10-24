"""Guardrails shared by the library, the logger and the ADK callbacks.

* confine(): path allowlist / root confinement (symlinks resolved).
* mask_text()/mask_obj(): output masking for every sink (reports, logs, ADK responses).
* contains_raw_secret(): input check used to keep raw secrets out of model inputs and tool args.
* safe_logger(): logger whose records are masked.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .detectors import find_matches
from .redaction import redact_line


class PathNotAllowed(PermissionError):
    pass


def default_root() -> Path | None:
    """Optional confinement root from SECRET_SCANNER_ROOT. None (unset) means any local path may be
    scanned; the scanner is read-only and every output is masked either way."""
    env = os.environ.get("SECRET_SCANNER_ROOT")
    return Path(env).expanduser().resolve() if env else None


def confine(path: str | Path, root: str | Path | None = None) -> Path:
    """Resolve `path` (symlinks followed). If a root is given (argument or SECRET_SCANNER_ROOT),
    require the path to be inside it; relative paths are taken relative to that root. With no
    root, any local path is allowed and relative paths resolve against the working directory.
    The error message never echoes more than the value the caller already supplied."""
    base = Path(root).expanduser().resolve() if root else default_root()
    p = Path(path).expanduser()
    p = (base / p) if (base and not p.is_absolute()) else p
    real = p.resolve()
    if base and real != base and base not in real.parents:
        raise PathNotAllowed(f"path is outside the allowed root ({base}); set SECRET_SCANNER_ROOT to change it")
    return real


def mask_text(text: str) -> str:
    """Redact every detected secret in free text (multi-line safe)."""
    if not text:
        return text
    return "\n".join(redact_line(l, max_len=10**9, skip_redacted=True) for l in text.split("\n"))


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v) for v in obj]
    return obj


def contains_raw_secret(text: str) -> bool:
    """True if `text` holds something that looks like an un-redacted secret.
    Entropy-only matches are ignored here (too noisy for chat text); already-redacted values
    (containing `****`) are fine."""
    for line in (text or "").split("\n"):
        for m in find_matches(line):
            if m.rule.name == "high_entropy_string" or "****" in m.value:
                continue
            return True
    return False


class _MaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = mask_text(record.getMessage())
            record.args = ()
        except Exception:  # never let logging break the scan, never leak either
            record.msg, record.args = "<log message suppressed>", ()
        return True


def safe_logger(name: str) -> logging.Logger:
    lg = logging.getLogger(name)
    if not any(isinstance(f, _MaskFilter) for f in lg.filters):
        lg.addFilter(_MaskFilter())
    return lg

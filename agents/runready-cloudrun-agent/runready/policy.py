"""RunReady's deterministic security core.

This module is the security boundary. It contains **no LLM calls** and depends
on nothing from Google ADK, so it can be unit-tested in full without any API
key. Every consequential operation in :mod:`runready.tools` delegates its
enforcement here.

Design rules (from the project spec):

* Workspace confinement: one explicit project root; all paths resolved against
  it; traversal and symlink-escape rejected; re-checked immediately before
  every read/write (never trust a string-prefix check alone).
* Secret minimization: protected paths denied by default; credential-like
  values redacted from any text before it reaches the model or an audit log.
* Patch integrity: a patch names its target, the expected original hash, and
  the exact change; it is rejected if the file changed since it was read.
* Fail-closed: ambiguity, policy violation, or malformed input => reject.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .schema import LEGAL_TRANSITIONS, PatchState


class PolicyError(Exception):
    """Raised when an operation violates a safety policy. Always fail-closed."""


# --------------------------------------------------------------------------- #
# Workspace confinement
# --------------------------------------------------------------------------- #

# Path components that are denied for both reading and writing, by default.
PROTECTED_NAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "credentials.json",
    }
)

# Suffixes that look like secrets / credentials.
PROTECTED_SUFFIXES: tuple[str, ...] = (".pem", ".key", ".pfx", ".p12")

# File types RunReady is allowed to *write* to (minimal-fix surface only).
WRITABLE_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ""}
)
# Bare config filenames (no suffix) that are writable, e.g. Procfile.
WRITABLE_NAMES: frozenset[str] = frozenset({"Procfile", "Dockerfile"})


def _is_protected(rel: Path) -> bool:
    """True if any component of the relative path is on the denylist."""
    if rel.name.startswith(".env"):
        return True
    if rel.suffix.lower() in PROTECTED_SUFFIXES:
        return True
    return any(part in PROTECTED_NAMES for part in rel.parts)


def resolve_in_workspace(root: str | os.PathLike[str], target: str | os.PathLike[str]) -> Path:
    """Resolve *target* to a real absolute path proven to live under *root*.

    Rejects path traversal and symlinks that escape the workspace. This is the
    single chokepoint every read and write must pass through, and it is called
    again immediately before the actual I/O so a mid-session symlink swap can't
    slip past an earlier check.

    Raises:
        PolicyError: if the resolved path escapes the workspace or is protected.
    """
    root_real = Path(root).resolve(strict=True)
    if not root_real.is_dir():
        raise PolicyError(f"workspace root is not a directory: {root_real}")

    # Resolve the full target with symlinks followed (strict=False so we can
    # also validate not-yet-created write targets); the containment check below
    # is what actually enforces safety.
    candidate = (root_real / target) if not Path(target).is_absolute() else Path(target)
    resolved = candidate.resolve(strict=False)

    # Containment via commonpath on *resolved* paths — not a string prefix.
    try:
        common = os.path.commonpath([str(root_real), str(resolved)])
    except ValueError:  # different drives / anchors
        raise PolicyError(f"path escapes workspace: {target}") from None
    if common != str(root_real):
        raise PolicyError(f"path escapes workspace: {target}")

    rel = resolved.relative_to(root_real)
    if _is_protected(rel):
        raise PolicyError(f"path is protected and may not be accessed: {rel}")

    # If any existing parent is a symlink pointing outside the workspace, reject.
    probe = resolved
    while probe != root_real and probe != probe.parent:
        if probe.is_symlink():
            link_real = probe.resolve(strict=False)
            try:
                c = os.path.commonpath([str(root_real), str(link_real)])
            except ValueError:
                raise PolicyError(f"symlink escapes workspace: {rel}") from None
            if c != str(root_real):
                raise PolicyError(f"symlink escapes workspace: {rel}")
        probe = probe.parent

    return resolved


def assert_writable(root: str | os.PathLike[str], target: str | os.PathLike[str]) -> Path:
    """Resolve a write target and confirm its type is on the write allowlist."""
    resolved = resolve_in_workspace(root, target)
    name = resolved.name
    if name not in WRITABLE_NAMES and resolved.suffix.lower() not in WRITABLE_SUFFIXES:
        raise PolicyError(f"file type not writable: {name}")
    return resolved


# --------------------------------------------------------------------------- #
# Secret minimization
# --------------------------------------------------------------------------- #

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # key = value style assignments for anything secret-ish
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*)"
        r"\s*[:=]\s*(\S+)"
    ),
    # Google API keys
    re.compile(r"AIza[0-9A-Za-z._\-]{10,}"),
    # Bearer tokens
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    # Private key blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)

_REDACTION = "[REDACTED]"


def redact_secrets(text: str) -> str:
    """Mask credential-like values in *text*.

    This is best-effort pattern matching and CANNOT prove all secrets are gone;
    the README documents that limitation. It exists so that logs and tool
    output passed to the model or written to an audit record do not carry
    obvious credentials.
    """
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 2:
            out = pat.sub(lambda m: f"{m.group(1)}={_REDACTION}", out)
        else:
            out = pat.sub(_REDACTION, out)
    return out


# --------------------------------------------------------------------------- #
# Bounded execution limits
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Limits:
    """Hard ceilings on everything the agent is allowed to consume."""

    max_turns: int = 12
    max_tool_calls: int = 40
    max_files_inspected: int = 200
    max_total_bytes: int = 2_000_000
    max_file_bytes: int = 200_000
    subprocess_timeout_s: float = 20.0
    max_output_bytes: int = 32_000
    max_retries: int = 2


DEFAULT_LIMITS = Limits()


@dataclass
class Budget:
    """Mutable counter guarding a single session against unbounded execution."""

    limits: Limits = field(default_factory=lambda: DEFAULT_LIMITS)
    _turns: int = 0
    _tool_calls: int = 0
    _bytes_read: int = 0
    _started: float = field(default_factory=time.monotonic)

    def charge_tool_call(self) -> None:
        self._tool_calls += 1
        if self._tool_calls > self.limits.max_tool_calls:
            raise PolicyError("tool-call budget exceeded; stopping (fail-closed)")

    def charge_turn(self) -> None:
        self._turns += 1
        if self._turns > self.limits.max_turns:
            raise PolicyError("turn budget exceeded; stopping (fail-closed)")

    def charge_bytes(self, n: int) -> None:
        self._bytes_read += n
        if self._bytes_read > self.limits.max_total_bytes:
            raise PolicyError("inspection byte budget exceeded; stopping (fail-closed)")


# --------------------------------------------------------------------------- #
# Patch integrity
# --------------------------------------------------------------------------- #


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text_capped(path: Path, limits: Limits = DEFAULT_LIMITS) -> str:
    """Read a file's text, enforcing the per-file size cap. Fail-closed on oversize."""
    size = path.stat().st_size
    if size > limits.max_file_bytes:
        raise PolicyError(f"file exceeds inspection cap ({size} bytes): {path.name}")
    return path.read_text(encoding="utf-8", errors="replace")


def validate_patch(
    root: str | os.PathLike[str],
    rel_target: str,
    expected_original_sha256: str,
    original_snippet: str,
    replacement_snippet: str,
    limits: Limits = DEFAULT_LIMITS,
) -> Path:
    """Deterministically validate a proposed patch. Reject on any uncertainty.

    Checks, in order: target resolves inside the workspace, is a writable type,
    currently exists, its on-disk hash matches what RunReady read, and the exact
    ``original_snippet`` is present. Returns the resolved path on success.

    Raises:
        PolicyError: on any failed check (stale file, wrong hash, missing
            snippet, out-of-scope path, non-writable type).
    """
    resolved = assert_writable(root, rel_target)
    if not resolved.exists():
        raise PolicyError(f"patch target does not exist: {rel_target}")

    current = read_text_capped(resolved, limits)
    if sha256_text(current) != expected_original_sha256:
        raise PolicyError(
            "stale patch: target file changed since it was read; regenerate the patch"
        )
    if original_snippet not in current:
        raise PolicyError("patch original snippet not found in current file")
    if original_snippet == replacement_snippet:
        raise PolicyError("patch is a no-op")
    return resolved


def apply_validated_patch(
    root: str | os.PathLike[str],
    rel_target: str,
    expected_original_sha256: str,
    original_snippet: str,
    replacement_snippet: str,
    limits: Limits = DEFAULT_LIMITS,
) -> None:
    """Re-validate then apply exactly one approved change.

    Re-runs :func:`validate_patch` immediately before writing (the file may have
    changed between validation and approval) and replaces only the first
    occurrence of ``original_snippet``. Any broader edit is impossible here.
    """
    resolved = validate_patch(
        root,
        rel_target,
        expected_original_sha256,
        original_snippet,
        replacement_snippet,
        limits,
    )
    current = read_text_capped(resolved, limits)
    updated = current.replace(original_snippet, replacement_snippet, 1)
    # Re-confirm containment right before the write (symlink-swap defense).
    resolve_in_workspace(root, rel_target)
    resolved.write_text(updated, encoding="utf-8")


def assert_transition(current: PatchState, nxt: PatchState) -> None:
    """Guard the patch lifecycle. Skipping or reversing a state is rejected."""
    if nxt not in LEGAL_TRANSITIONS[current]:
        raise PolicyError(f"illegal patch transition {current.value} -> {nxt.value}")

"""Rules R07, R08: secret scanning and file hygiene."""
from __future__ import annotations

import re
from pathlib import Path

from ..models import Finding, Severity

# ---------------------------------------------------------------------------
# R07 – secret patterns
# Each entry: (label, compiled_regex, check_placeholder)
# Evidence is always redacted: first 4 chars + "..."
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern, bool]] = [
    # Google API key: AIza... (39 chars)
    (
        "Google API key",
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        False,
    ),
    # OpenAI: sk-... (≥20 chars)
    (
        "OpenAI key (sk-...)",
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        False,
    ),
    # GitHub token: ghp_/gho_/ghs_/ghr_/github_pat_
    (
        "GitHub token",
        re.compile(r"(ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}"),
        False,
    ),
    # AWS access key ID: AKIA... (20 chars)
    (
        "AWS access key ID",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        False,
    ),
    # PEM private key block
    (
        "PEM private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        False,
    ),
    # Slack token: xox[baprs]-...
    (
        "Slack token",
        re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
        False,
    ),
    # Generic KEY/SECRET/TOKEN/PASSWORD assignment with a long literal (≥16 non-whitespace chars)
    (
        "Generic secret assignment",
        re.compile(
            r'(?:KEY|SECRET|TOKEN|PASSWORD)\s*=\s*["\']?([A-Za-z0-9+/\-_=!@#$%^&*]{16,})["\']?',
            re.IGNORECASE,
        ),
        True,  # allow obvious placeholders
    ),
]

# Obvious placeholder values that R07 should ignore (case-insensitive substring match)
_PLACEHOLDER_MARKERS = (
    "your_",
    "_here",
    "example",
    "placeholder",
    "xxxxxxxx",
    "changeme",
    "<",
    ">",
    "...",
    "your-",
    "enter_",
    "insert_",
)

# R08 – hygiene: directories and file patterns to flag
_HYGIENE_DIR_NAMES = frozenset(
    {
        "venv",
        ".venv",
        "env",
        "node_modules",
        "__pycache__",
    }
)
_HYGIENE_SUFFIXES = frozenset({".sqlite", ".db", ".pem", ".key"})
_HYGIENE_NAMES = frozenset({".env"})

# Binary file sniff: skip files whose first 512 bytes contain null bytes
_BINARY_CHUNK = 512

# Max file size to scan (4 MB)
_MAX_SCAN_BYTES = 4 * 1024 * 1024

# Dirs to skip (secrets scanner)
_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "tests",  # test files may contain fake-secret strings by design
    }
)


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:_BINARY_CHUNK]
        return b"\x00" in chunk
    except OSError:
        return True


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(marker in low for marker in _PLACEHOLDER_MARKERS)


def _redact(value: str) -> str:
    """Return first 4 chars + ellipsis."""
    if len(value) <= 4:
        return "****"
    return value[:4] + "..."


def scan_secrets(project_path: Path) -> list[Finding]:
    """R07: scan every text file for secret patterns."""
    findings: list[Finding] = []

    for path in _iter_text_files(project_path):
        try:
            if path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern, placeholder_ok in _SECRET_PATTERNS:
                for m in pattern.finditer(line):
                    value = m.group(0)
                    if placeholder_ok and _is_placeholder(value):
                        continue
                    # For generic assignment pattern, check the captured group
                    if placeholder_ok and m.lastindex and _is_placeholder(m.group(1)):
                        continue
                    findings.append(
                        Finding(
                            rule_id="R07",
                            severity=Severity.ERROR,
                            file=path.relative_to(project_path),
                            line=lineno,
                            message=f"Possible secret detected: {label}",
                            evidence=_redact(value),
                            fix_hint=(
                                "Remove this secret. Use .env for real keys "
                                "and only commit .env.example with placeholders."
                            ),
                        )
                    )

    return findings


def _load_gitignore_lines(project_path: Path) -> list[str]:
    """Return stripped, non-empty, non-comment lines from .gitignore."""
    gi = project_path / ".gitignore"
    if not gi.exists():
        return []
    return [
        ln.strip()
        for ln in gi.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _covered(gi_lines: list[str], name: str) -> bool:
    """Return True if 'name' (a file/dir name) appears to be covered by a .gitignore pattern."""
    for p in gi_lines:
        p_stripped = p.rstrip("/")
        # Exact match or with trailing slash
        if p_stripped == name or p == name + "/":
            return True
        # **/<name> or <prefix>/<name>
        if p_stripped.endswith("/" + name):
            return True
        # Glob: *.ext
        if name.startswith(".") and p == "*" + name:
            return True
        # .env.* covers .env variants
        if p_stripped.startswith(name + ".") or p_stripped.startswith(name + "/"):
            return True
    return False


def check_hygiene(project_path: Path) -> list[Finding]:
    """R08: flag .env files, venvs, node_modules, __pycache__, db/pem/key files
    that are NOT covered by .gitignore. Also verify .gitignore covers .env and venvs."""
    findings: list[Finding] = []

    # Load .gitignore patterns first (so we can skip covered items)
    gi_lines = _load_gitignore_lines(project_path)

    # Check for files/dirs that shouldn't be committed and aren't gitignored
    for item in project_path.rglob("*"):
        try:
            rel = item.relative_to(project_path)
        except ValueError:
            continue

        parts = rel.parts
        # Skip if inside a known skip dir (other than the first component being one we flag)
        if len(parts) > 1 and any(p in _SKIP_DIRS for p in parts[:-1]):
            continue

        if item.is_dir():
            if item.name in _HYGIENE_DIR_NAMES:
                # Ephemeral __pycache__ generated by python runtime is ignored if gitignored
                if item.name == "__pycache__" and _covered(gi_lines, "__pycache__"):
                    continue
                is_cov = _covered(gi_lines, item.name)
                findings.append(
                    Finding(
                        rule_id="R08",
                        severity=Severity.WARNING if is_cov else Severity.ERROR,
                        file=rel,
                        line=None,
                        message=f"Directory '{item.name}' should not be committed.",
                        evidence=str(rel),
                        fix_hint=f"Add '{item.name}/' to .gitignore and remove it from git tracking.",
                    )
                )
        else:
            if item.name in _HYGIENE_NAMES:
                # Real .env file should never exist in contribution folder
                findings.append(
                    Finding(
                        rule_id="R08",
                        severity=Severity.ERROR,
                        file=rel,
                        line=None,
                        message=f"File '{item.name}' (likely contains secrets) must not be committed.",
                        evidence=str(rel),
                        fix_hint="Remove this file from git tracking and add it to .gitignore.",
                    )
                )
            elif item.suffix in _HYGIENE_SUFFIXES:
                if _covered(gi_lines, "*" + item.suffix) or _covered(gi_lines, item.name):
                    continue
                findings.append(
                    Finding(
                        rule_id="R08",
                        severity=Severity.WARNING,
                        file=rel,
                        line=None,
                        message=f"Sensitive/binary file '{item.name}' should not be committed.",
                        evidence=str(rel),
                        fix_hint=f"Add '*{item.suffix}' to .gitignore and remove from tracking.",
                    )
                )

    # Verify .gitignore covers .env and venvs
    gitignore = project_path / ".gitignore"
    if gitignore.exists():
        if not _covered(gi_lines, ".env"):
            findings.append(
                Finding(
                    rule_id="R08",
                    severity=Severity.WARNING,
                    file=Path(".gitignore"),
                    line=None,
                    message=".gitignore does not appear to cover .env files.",
                    evidence=None,
                    fix_hint="Add '.env' to .gitignore.",
                )
            )

        venv_covered = any(_covered(gi_lines, v) for v in (".venv", "venv", "env"))
        if not venv_covered:
            findings.append(
                Finding(
                    rule_id="R08",
                    severity=Severity.WARNING,
                    file=Path(".gitignore"),
                    line=None,
                    message=".gitignore does not appear to cover virtual environment directories.",
                    evidence=None,
                    fix_hint="Add '.venv/', 'venv/', or 'env/' to .gitignore.",
                )
            )

    return findings


def _iter_text_files(project_path: Path):
    """Yield all non-binary files under project_path, skipping .git and known dirs."""
    for path in project_path.rglob("*"):
        if not path.is_file():
            continue
        # Skip dirs in path
        try:
            rel_parts = path.relative_to(project_path).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if _is_binary(path):
            continue
        yield path

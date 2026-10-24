"""Checks for secret exposure, credential leakage, and untracked environment artifacts (S01, S02)."""

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import ProjectContext

KNOWN_KEY_PATTERNS = [
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{30,45}")),
    ("OpenAI API Key", re.compile(r"sk-(?:proj-)?[a-zA-Z0-9\-_]{20,}")),
    ("GitHub Token", re.compile(r"(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{50,})")),
    ("AWS Access Key", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}")),
    ("Anthropic API Key", re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}")),
    ("Private Key Block", re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP)?\s?PRIVATE KEY-----")),
]

KEY_CONTEXT_PATTERN = re.compile(
    r"(?:api[_\-]?key|secret|token|password|auth|bearer|credential|client[_\-]?secret)\s*[:=]\s*['\"]?([A-Za-z0-9+/_\-]{20,})['\"]?",
    re.IGNORECASE,
)

UUID_PATTERN = re.compile(r"^(?:urn:uuid:)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HEX_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{32,64}$")

PLACEHOLDER_SUBSTRINGS = [
    "your_",
    "<your",
    "placeholder",
    "example",
    "dummy",
    "fake",
    "xxxx",
    "insert_",
    "replace_with",
    "todo",
    "sample",
    "none",
    "null",
    "test_key",
    "changeme",
    "my_key",
    "my-key",
]

FORBIDDEN_TRACKED_EXTENSIONS = {".sqlite", ".sqlite3", ".db", ".db3", ".pyc", ".pyo"}
FORBIDDEN_TRACKED_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".sqlite", ".sqlite3", ".db", ".db3", ".bin", ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".eot",
}


def shannon_entropy(data: str) -> float:
    """Compute Shannon entropy in bits per character."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    counts: dict[str, int] = {}
    for ch in data:
        counts[ch] = counts.get(ch, 0) + 1
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def redact_secret(val: str) -> str:
    """Safely redact secret values in findings, error messages, and logs."""
    if not val:
        return ""
    text = str(val)

    # 1. Scan and redact any embedded known key patterns
    for _, pat in KNOWN_KEY_PATTERNS:
        def repl(match: re.Match[str]) -> str:
            matched = match.group(0)
            if is_placeholder(matched):
                return matched
            if len(matched) <= 8:
                return "[REDACTED]"
            return f"{matched[:4]}...{matched[-4:]} [REDACTED]"
        text = pat.sub(repl, text)

    # 2. If the string itself was passed as a single candidate secret token
    if text == str(val):
        clean = text.strip().strip("'\"")
        if len(clean) > 8 and not is_placeholder(clean):
            if shannon_entropy(clean) >= 4.0 and len(clean) >= 20 and not UUID_PATTERN.match(clean) and not HEX_HASH_PATTERN.match(clean):
                return f"{clean[:4]}...{clean[-4:]} [REDACTED]"
            return f"{clean[:4]}...{clean[-4:]} [REDACTED]"
        elif len(clean) <= 8:
            return "[REDACTED]"

    return text


def is_placeholder(val: str) -> bool:
    """Check if string is an obvious documentation or test placeholder."""
    val_lower = val.lower().strip("'\"")
    if val_lower.startswith("<") and val_lower.endswith(">"):
        return True
    if val_lower.startswith("${") and val_lower.endswith("}"):
        return True
    if val_lower.startswith("$"):
        return True
    if val_lower.startswith("[") and val_lower.endswith("]"):
        return True
    return any(p in val_lower for p in PLACEHOLDER_SUBSTRINGS)


def check_s01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """S01: Detect tracked .env files and hard-coded credentials/keys."""
    rule_id = "S01"
    name = "Zero Secrets Policy"
    source = config.get("source_rule", "CONTRIBUTING.md Quality & Security Standards")
    findings: list[Finding] = []

    # 1. Check for committed or present real environment files (.env*)
    all_env_candidates = set(ctx.tracked_files) | {p.as_posix() for p in ctx.files}
    for cand in all_env_candidates:
        posix = cand.replace("\\", "/")
        name_only = posix.split("/")[-1]
        is_env_file = (
            name_only == ".env"
            or (name_only.startswith(".env.") and not name_only.endswith(".example"))
            or (name_only.endswith(".env") and not name_only.endswith(".example"))
        )
        if is_env_file and name_only != ".env.example":
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=f"Real environment file '{name_only}' detected in project.",
                    path=posix,
                    evidence=f"File '{posix}' violates the repository zero-secrets policy.",
                    fix=f"Remove '{posix}' and ensure it is in .gitignore. Use .env.example with placeholders only.",
                    source_rule=source,
                )
            )

    # 2. Scan text files for hard-coded credentials
    for rel_path in ctx.files:
        posix_str = rel_path.as_posix()
        # Skip binary / non-text
        if rel_path.suffix.lower() in BINARY_EXTENSIONS:
            continue

        content = ctx.read_text(rel_path)
        if content is None:
            continue

        # In .env.example, placeholders are allowed and expected
        is_env_example = rel_path.name == ".env.example"

        for line_num, line in enumerate(content.splitlines(), 1):
            line_str = line.strip()
            if not line_str:
                continue

            # In .env.example, lines starting with # are comments or commented variables
            if is_env_example and (line_str.startswith("#") or is_placeholder(line_str)):
                continue

            # Check known prefix patterns
            matched_pattern = False
            for pat_name, pat in KNOWN_KEY_PATTERNS:
                match = pat.search(line_str)
                if match:
                    matched_text = match.group(0)
                    if is_placeholder(matched_text):
                        continue
                    matched_pattern = True
                    redacted = redact_secret(matched_text)
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.ERROR,
                            message=f"Possible hard-coded credential detected ({pat_name}).",
                            path=posix_str,
                            line=line_num,
                            evidence=f"Matched {pat_name}: {redacted}",
                            fix="Remove credential from source code. Load secrets from environment variables at runtime.",
                            source_rule=source,
                        )
                    )
                    break

            if matched_pattern:
                continue

            # Context-gated Shannon entropy check
            ctx_match = KEY_CONTEXT_PATTERN.search(line_str)
            if ctx_match:
                candidate = ctx_match.group(1).strip()
                if is_placeholder(candidate):
                    continue
                # Negative controls: ignore UUIDs and git commits/hashes
                if UUID_PATTERN.match(candidate) or (HEX_HASH_PATTERN.match(candidate) and ("id" in line_str.lower() or "sha" in line_str.lower() or "commit" in line_str.lower())):
                    continue

                entropy = shannon_entropy(candidate)
                # Strict 4.0 bits/char floor
                if entropy >= 4.0 and len(candidate) >= 20:
                    redacted = redact_secret(candidate)
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.ERROR,
                            message=f"High-entropy secret string detected (entropy: {entropy:.2f} bits/char).",
                            path=posix_str,
                            line=line_num,
                            evidence=f"Context: {ctx_match.group(0).split(':')[0].split('=')[0]} = {redacted}",
                            fix="Remove secret from code. Store in environment variables via .env and load securely.",
                            source_rule=source,
                        )
                    )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.FAIL, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)


def check_s02(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """S02: Check that no virtual environments or local databases are tracked."""
    rule_id = "S02"
    name = "No Virtual Environments or Local Databases"
    source = config.get("source_rule", "CONTRIBUTING.md Step 8")
    findings: list[Finding] = []

    files_to_check = set(ctx.tracked_files) | {p.as_posix() for p in ctx.files}

    for path_str in files_to_check:
        posix = path_str.replace("\\", "/")
        parts = posix.split("/")

        # Check directory names
        for part in parts[:-1]:
            if part in FORBIDDEN_TRACKED_DIRS:
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=Severity.ERROR,
                        message=f"Virtual environment or dependency directory '{part}' is tracked.",
                        path=posix,
                        evidence=f"Found tracked artifact inside '{part}/'.",
                        fix=f"Untrack '{part}/' from Git and ensure it is included in your .gitignore.",
                        source_rule=source,
                    )
                )
                break

        # Check file extension
        suffix = Path(posix).suffix.lower()
        if suffix in FORBIDDEN_TRACKED_EXTENSIONS:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=f"Local database or compiled binary artifact '{Path(posix).name}' is tracked.",
                    path=posix,
                    evidence=f"File extension '{suffix}' should not be committed to the repository.",
                    fix=f"Remove '{posix}' from Git tracking and add '*{suffix}' to your .gitignore.",
                    source_rule=source,
                )
            )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.FAIL, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)

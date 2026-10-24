"""Security checks: secret detection in prompts and output invariants."""

from __future__ import annotations

import re

# Common credential formats. The goal is to warn the user before a prompt
# with a live secret goes to a model provider, not to be an exhaustive scanner.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(proj-)?[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("AWS access key id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
]


def find_secrets(text: str) -> list[str]:
    """Return the names (never the values) of credential types found in ``text``."""
    found: list[str] = []
    for name, pat in SECRET_PATTERNS:
        if pat.search(text) and name not in found:
            found.append(name)
    # An Anthropic key also matches the generic OpenAI "sk-" shape; report it once.
    if "Anthropic API key" in found and "OpenAI API key" in found:
        if not any(m.group(0).startswith("sk-") and not m.group(0).startswith("sk-ant-")
                   for m in SECRET_PATTERNS[1][1].finditer(text)):
            found.remove("OpenAI API key")
    return found


def preserves_original(original: str, enhanced: str, constraints: list[str]) -> bool:
    """Invariant for rewrite mode: the user's prompt and every constraint survive verbatim."""
    if original not in enhanced:
        return False
    return all(c in enhanced for c in constraints)

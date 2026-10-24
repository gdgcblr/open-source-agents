"""Secret detection shared by check X2 and the AI redaction guardrail.

Provider patterns are high-confidence (error). The generic `name = value`
pattern is a heuristic (warn) and is filtered by placeholder words and entropy.
The eval in evals/run_secrets_eval.py measures both against generated keys and
look-alike decoys; run it after changing anything here.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .models import Severity


@dataclass(frozen=True)
class SecretPattern:
    id: str
    name: str
    regex: re.Pattern[str]
    severity: Severity


PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern("google_api_key", "Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])"), Severity.ERROR),
    SecretPattern("anthropic_key", "Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), Severity.ERROR),
    SecretPattern("openai_key", "OpenAI API key",
                  re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{32,}"), Severity.ERROR),
    SecretPattern("github_token", "GitHub token",
                  re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"), Severity.ERROR),
    SecretPattern("aws_access_key", "AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), Severity.ERROR),
    SecretPattern("slack_token", "Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), Severity.ERROR),
    SecretPattern("huggingface_token", "Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b"), Severity.ERROR),
    SecretPattern("private_key", "Private key block",
                  re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"), Severity.ERROR),
)

_GENERIC = re.compile(
    r"""(?ix)
    \b([a-z0-9_]*(?:api[_-]?key|secret|token|passwd|password|auth[_-]?key|access[_-]?key)[a-z0-9_]*)
    \s*[:=]\s*
    ["']?([A-Za-z0-9_\-+/=.]{16,})["']?
    """
)
_PLACEHOLDER_WORDS = ("your", "example", "placeholder", "changeme", "change_me", "xxxx", "dummy", "sample",
                      "here", "replace", "insert", "redacted", "<", "${", "env", "getenv", "process",
                      "secret", "test", "fake", "mock")  # last four: PR #33
GENERIC_ENTROPY_THRESHOLD = 3.5

# Provider-format matches that are clearly not real secrets are reported as info, not errors.
# Each rule was added after a false alarm on a real PR.
_FAKE_WORDS = ("fake", "dummy", "placeholder", "example", "sample", "notreal", "not_real", "redacted")
_PEM_BODY = re.compile(r"[A-Za-z0-9+/=]{40,}")
FAKE_RUN_LENGTH = 6  # e.g. "abcdef", "123456", "aaaaaa"; random keys essentially never contain these


def _has_run(value: str, length: int = FAKE_RUN_LENGTH) -> bool:
    """True if value contains `length` consecutive ascending (abc, 123) or repeated (aaa) characters."""
    up = same = 1
    for a, b in zip(value, value[1:]):
        up = up + 1 if ord(b) - ord(a) == 1 and a.isalnum() and b.isalnum() else 1
        same = same + 1 if a == b and a.isalnum() else 1
        if up >= length or same >= length:
            return True
    return False


def _not_a_secret(pattern_id: str, value: str, rest_of_line: str, next_line: str) -> str | None:
    """Why a provider-format match is clearly not a real secret, or None."""
    if pattern_id == "aws_access_key" and value.endswith("EXAMPLE"):
        return "published documentation example"  # AWS's own docs key (PR #17)
    if pattern_id == "private_key":
        if not (_PEM_BODY.search(rest_of_line) or _PEM_BODY.search(next_line)):
            return "header only, no key material"  # guardrail tests (PRs #43, #48)
        return None
    lowered = value.lower()
    if any(word in lowered for word in _FAKE_WORDS) or _has_run(value):
        return "looks like a fake test value"  # e.g. sequential test tokens (PRs #33, #42, #43)
    return None


@dataclass(frozen=True)
class SecretMatch:
    pattern_id: str
    name: str
    severity: Severity
    line: int
    start: int
    end: int
    value: str
    not_secret_reason: str | None = None  # set when the match is clearly not a real secret

    @property
    def is_example(self) -> bool:
        return self.not_secret_reason is not None

    @property
    def masked(self) -> str:
        return mask(self.value)


def mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-3:]}"


def shannon_entropy(value: str) -> float:
    counts = Counter(value)
    total = len(value)
    return -sum(c / total * math.log2(c / total) for c in counts.values())


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(word in lowered for word in _PLACEHOLDER_WORDS) or len(set(value)) <= 3


def scan(text: str) -> list[SecretMatch]:
    matches: list[SecretMatch] = []
    # split("\n") rather than splitlines() so line numbers match redact().
    lines = text.split("\n")
    for number, line in enumerate(lines, start=1):
        taken: list[tuple[int, int]] = []
        next_line = lines[number] if number < len(lines) else ""
        for pattern in PATTERNS:
            for m in pattern.regex.finditer(line):
                taken.append(m.span())
                reason = _not_a_secret(pattern.id, m.group(0), line[m.end():], next_line)
                matches.append(SecretMatch(
                    pattern.id,
                    f"{pattern.name} ({reason})" if reason else pattern.name,
                    Severity.INFO if reason else pattern.severity,
                    number, m.start(), m.end(), m.group(0), reason,
                ))
        for m in _GENERIC.finditer(line):
            value = m.group(2)
            start, end = m.span(2)
            if any(s <= start < e for s, e in taken):
                continue  # already reported by a provider pattern
            if _looks_like_placeholder(value):
                continue
            has_letters = any(c.isalpha() for c in value)
            has_digits = any(c.isdigit() for c in value)
            if not (has_letters and has_digits) or shannon_entropy(value) < GENERIC_ENTROPY_THRESHOLD:
                continue
            matches.append(SecretMatch("generic_secret", f"Possible secret in '{m.group(1)}'", Severity.WARN,
                                       number, start, end, value))
    return matches


def redact(text: str) -> tuple[str, int]:
    """Replace every detected secret with [REDACTED]. Returns (text, number of redactions)."""
    out_lines = []
    count = 0
    lines = text.split("\n")
    by_line: dict[int, list[SecretMatch]] = {}
    for match in scan(text):
        by_line.setdefault(match.line, []).append(match)
    for number, line in enumerate(lines, start=1):
        for match in sorted(by_line.get(number, []), key=lambda m: m.start, reverse=True):
            line = line[: match.start] + "[REDACTED]" + line[match.end :]
            count += 1
        out_lines.append(line)
    return "\n".join(out_lines), count

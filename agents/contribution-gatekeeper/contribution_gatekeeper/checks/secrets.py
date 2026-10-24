"""Leaked-credential detection. Values are always masked in findings so a
review comment never re-publishes the secret it found."""

from __future__ import annotations

import math
import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy

VENDOR_PATTERNS = {
    "Google API key": r"AIza[0-9A-Za-z_\-]{35}|\bAQ\.[0-9A-Za-z_\-]{40,}",
    "OpenAI API key": r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}",
    "Anthropic API key": r"sk-ant-[A-Za-z0-9_\-]{32,}",
    "GitHub token": r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}",
    "AWS access key": r"(?:AKIA|ASIA)[0-9A-Z]{16}",
    "Slack token": r"xox[abprs]-[A-Za-z0-9-]{10,}",
    "Hugging Face token": r"hf_[A-Za-z0-9]{34}",
    "Private key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----",
}
GENERIC = re.compile(
    r"""(?i)\b([A-Z0-9_]*(?:api[_-]?key|secret|token|passw(?:or)?d))\b\s*[:=]\s*["']?([A-Za-z0-9_\-./+=]{16,})"""
)
PLACEHOLDER = re.compile(r"(?i)your|xxx|example|placeholder|changeme|dummy|fake|<|\*\*\*|replace|sample|test")
SECRET_FILES = re.compile(r"(^|/)(\.env(\.(?!example$)[\w.-]+)?|credentials\.json|service-account[\w.-]*\.json|id_rsa\w*|[\w.-]+\.(pem|key|p12|pfx))$")


def _entropy(s: str) -> float:
    return -sum((s.count(c) / len(s)) * math.log2(s.count(c) / len(s)) for c in set(s))


def mask(v: str) -> str:
    return v[:4] + "…" + f"({len(v)} chars)" if len(v) > 8 else "****"


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    for f in sub.project_files():
        rel = str(f.relative_to(sub.root))
        if SECRET_FILES.search(rel):
            out.append(Finding(
                "secrets.env-file", Severity.BLOCKER, Criterion.SECURITY,
                f"`{rel}` is a secrets file and must never be committed.", file=rel,
                fix=f"git rm --cached {rel} && add it to .gitignore, then rotate any credential it contained.",
                rule=policy.rule("secrets.env-file"),
            ))
            continue
        if f.stat().st_size > 1_000_000:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            hit = None
            for name, pat in VENDOR_PATTERNS.items():
                m = re.search(pat, line)
                if m:
                    hit = (name, m.group(0))
                    break
            if not hit:
                m = GENERIC.search(line)
                if m and not PLACEHOLDER.search(m.group(2)) and _entropy(m.group(2)) > 3.5:
                    hit = (f"possible secret in `{m.group(1)}`", m.group(2))
            if hit:
                out.append(Finding(
                    "secrets.leaked", Severity.BLOCKER, Criterion.SECURITY,
                    f"{hit[0]} committed: `{mask(hit[1])}`.", file=rel, line=n,
                    fix="Remove it, load it from an environment variable instead, and ROTATE the key: "
                        "it is already public in the PR history.",
                    rule=policy.rule("secrets.leaked"),
                ))
    return out

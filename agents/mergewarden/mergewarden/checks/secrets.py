"""Leaked-credential detection. Values are always masked in findings so a
review comment never re-publishes the secret it found.

Scanned: every file in the project (any encoding), changed files outside it,
and every line added anywhere in the PR's history. Each line is also checked
with string concatenations joined and base64 tokens decoded.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from typing import Iterator, Optional

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
# group(1) = variable name, group(2) = value. Quoted values may contain any
# non-quote characters (passwords like `Xk9#...`); bare values must look like a token.
GENERIC = re.compile(
    r"""(?i)\b([A-Z0-9_]*(?:api[_-]?key|secret|token|passw(?:or)?d))\b["']?\s*[:=]\s*["']?"""
    r"""((?<=["'])[^"'\s]{12,}|[A-Za-z0-9_\-./+=]{16,})"""
)
# A value is a placeholder only if the WHOLE value is one ("your_key_here"),
# not if it merely contains "your" or "test" somewhere ("Xk9#latest7...").
PLACEHOLDER = re.compile(
    r"""(?i)^(?:<[^>]*>|\$\{?\w+\}?|\{\{.*\}\}|x{3,}\w*|\*{3,}|\.{3,}|(?:your|my|the)[\w.\-]*|"""
    r"""[\w.\-]*(?:example|placeholder|changeme|change_me|dummy|fake|replace|sample|redacted|here)[\w.\-]*|"""
    r"""test|testing|todo|none|null|secret|password|token)$"""
)
SECRET_FILES = re.compile(r"(^|/)(\.env(\.(?!example$)[\w.-]+)?|credentials\.json|service-account[\w.-]*\.json|id_rsa\w*|[\w.-]+\.(pem|key|p12|pfx))$")
CREDENTIAL_JSON = re.compile(r'"type"\s*:\s*"service_account"|"private_key"\s*:\s*"')
NOT_A_SECRET = re.compile(r"(?i)^(?:[a-z][\w+.-]*://|/|\./|\.\./|~/|os\.|process\.env|env\.)")  # URLs, paths, lookups
CONCAT = re.compile(r"""(["'])\s*\+?\s*\1""")  # "abc" + "def"  and  "abc" "def"
B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
SCAN_LIMIT = 2_000_000  # bytes per file
LEET = str.maketrans("013457", "oieast")
# Documented fake-credential conventions, e.g. AWS's AKIAIOSFODNN7EXAMPLE, or "N0tR3al" in test fixtures.
SYNTHETIC = re.compile(r"example|notreal|notavalid|fakekey|dummykey|synthetic|placeholder")
PEM_BODY = re.compile(r"^[A-Za-z0-9+/=]{40,}$")


def synthetic(value: str) -> bool:
    """A value that announces itself as fake. Anyone can add the word, so this only
    affects values that also match a vendor pattern, never a generic high-entropy hit."""
    return bool(SYNTHETIC.search(value.lower().translate(LEET)))


def _entropy(s: str) -> float:
    return -sum((s.count(c) / len(s)) * math.log2(s.count(c) / len(s)) for c in set(s))


def mask(v: str) -> str:
    return v[:4] + "…" + f"({len(v)} chars)" if len(v) > 8 else "****"


def _decoded_b64(line: str) -> Iterator[str]:
    for tok in B64.findall(line):
        try:
            raw = base64.b64decode(tok + "=" * (-len(tok) % 4), validate=True)
        except (binascii.Error, ValueError):
            continue
        text = raw.decode("utf-8", "replace")
        if text and sum(c.isprintable() for c in text) / len(text) > 0.9:
            yield text


def scan_line(line: str) -> Optional[tuple[str, str]]:
    """(what, value) for the first secret in a line, trying joined and decoded variants."""
    variants = [(line, "")]
    joined = CONCAT.sub("", line)
    if joined != line:
        variants.append((joined, " (split across strings)"))
    variants += [(d, " (base64-encoded)") for d in _decoded_b64(line)]
    for text, how in variants:
        for name, pat in VENDOR_PATTERNS.items():
            m = re.search(pat, text)
            if m and not synthetic(m.group(0)):
                return name + how, m.group(0)
    for text, how in variants[:2]:  # generic rule on raw + joined text only (decoded noise is too high)
        m = GENERIC.search(text)
        if (m and not PLACEHOLDER.search(m.group(2)) and not NOT_A_SECRET.match(m.group(2))
                and _entropy(m.group(2)) > 3.5):
            return f"possible secret in `{m.group(1)}`{how}", m.group(2)
    return None


def read_text(path) -> str:
    """Any file as text: undecodable bytes are replaced, never a reason to skip."""
    with open(path, "rb") as fh:
        return fh.read(SCAN_LIMIT).decode("utf-8", "replace")


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    seen: set[str] = set()

    def leaked(what: str, value: str, rel: str, line: Optional[int], extra: str = "") -> None:
        seen.add(value)
        out.append(Finding(
            "secrets.leaked", Severity.BLOCKER, Criterion.SECURITY,
            f"{what} committed{extra}: `{mask(value)}`.", file=rel, line=line,
            fix="Remove it, load it from an environment variable instead, and ROTATE the key: "
                "it is already public in the PR history.",
            rule=policy.rule("secrets.leaked"),
        ))

    files = list(sub.project_files())
    in_project = {str(f.relative_to(sub.root)) for f in files}
    for rel in sub.changed_files:  # a key in a root file is still a leak
        p = sub.root / rel
        if rel not in in_project and p.is_file() and (sub.tracked is None or rel in sub.tracked):
            files.append(p)

    for f in files:
        rel = str(f.relative_to(sub.root))
        if SECRET_FILES.search(rel):
            out.append(Finding(
                "secrets.env-file", Severity.BLOCKER, Criterion.SECURITY,
                f"`{rel}` is a secrets file and must never be committed.", file=rel,
                fix=f"git rm --cached {rel} && add it to .gitignore, then rotate any credential it contained.",
                rule=policy.rule("secrets.env-file"),
            ))
            continue
        try:
            text = read_text(f)
        except OSError as e:
            out.append(Finding("secrets.unreadable", Severity.MINOR, Criterion.SECURITY,
                               f"`{rel}` could not be read for the secret scan ({e.strerror}).", file=rel))
            continue
        if f.suffix.lower() == ".json" and CREDENTIAL_JSON.search(text):
            out.append(Finding(
                "secrets.env-file", Severity.BLOCKER, Criterion.SECURITY,
                f"`{rel}` is a cloud credential file (service account / private key) and must never be committed.",
                file=rel, fix=f"git rm --cached {rel}, add it to .gitignore, and revoke the key in your cloud console.",
                rule=policy.rule("secrets.env-file"),
            ))
            continue
        if f.stat().st_size > SCAN_LIMIT:
            out.append(Finding("secrets.partial-scan", Severity.INFO, Criterion.SECURITY,
                               f"`{rel}` is larger than {SCAN_LIMIT // 1_000_000} MB; only the start was scanned for secrets.",
                               file=rel))
        for n, line in enumerate(text.splitlines(), 1):
            hit = scan_line(line)
            if hit:
                leaked(hit[0], hit[1], rel, n)

    # Keys added in an earlier commit and deleted later are still public.
    added = sub.history_added or []
    for i, (commit, path, line) in enumerate(added):
        hit = scan_line(line)
        if hit and hit[0].startswith("Private key"):
            # A bare PEM header (e.g. a test fixture) is only a leak if key material follows it.
            nxt = added[i + 1] if i + 1 < len(added) else None
            if not (nxt and nxt[1] == path and PEM_BODY.match(nxt[2].strip().strip("\"',"))):
                hit = None
        if hit and hit[1] not in seen:
            seen.add(hit[1])
            out.append(Finding(
                "secrets.history", Severity.BLOCKER, Criterion.SECURITY,
                f"{hit[0]} is in the PR's commit history (commit {commit[:7]}, `{path}`): `{mask(hit[1])}`. "
                "Deleting it in a later commit does not unpublish it.",
                file=path or None,
                fix="Rotate the key now. Then rewrite the branch history (e.g. interactive rebase or git filter-repo) "
                    "and force-push.",
                rule=policy.rule("secrets.leaked"),
            ))
    if sub.history_note:
        out.append(Finding("secrets.history-unscanned", Severity.INFO, Criterion.SECURITY,
                           f"PR history was not fully scanned for secrets: {sub.history_note}."))
    return out

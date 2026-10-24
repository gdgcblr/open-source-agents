"""Best-effort secret redaction and argument guardrails for agent tool calls.

These are conservative regex checks, NOT a security boundary: they miss
encoded, split or unfamiliar secrets and can be bypassed by a determined
caller. Use them as a tripwire on top of real sandboxing and least privilege.
Matched secret values are never returned or logged, only their labels.
"""

import re

SECRET_PATTERNS = [
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
]

DANGER_PATTERNS = [
    ("path_traversal", re.compile(r"(?:^|[\\/\s\"'])\.\.(?:[\\/]|$)")),
    ("destructive_command", re.compile(
        r"\brm\s+-[a-zA-Z]*(?:r[a-zA-Z]*f|f[a-zA-Z]*r)"  # rm -rf / rm -fr
        r"|\bmkfs(?:\.\w+)?\b"
        r"|\bdd\s+.*\bof=/dev/"
        r"|:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"  # fork bomb
        r"|\bformat\s+[a-zA-Z]:"
        # shutdown/reboot as a command (alone, or with a flag/"now"/time), not in prose
        r"|(?:^|[;&|]\s*)(?:sudo\s+)?(?:shutdown|reboot)(?=\s*$|\s+(?:[-/]|now\b|\+?\d))"
        r"|\bdel\s+/[sS]\b"
        r"|\bdrop\s+(?:table|database)\b", re.IGNORECASE)),
]

# .env or .env.<anything> as a path component, except the safe .env.example
ENV_FILE = re.compile(r"(?:^|[\\/\s\"'=])\.env(?!\.example\b)(?:\.[\w-]+)?(?=$|[\s\"';])")


def redact(text):
    """Return (redacted_text, labels_found). Values are replaced by [REDACTED:<label>]."""
    found = []
    for label, pattern in SECRET_PATTERNS:
        text, n = pattern.subn(f"[REDACTED:{label}]", text)
        found += [label] * n
    return text, found


def redact_obj(obj):
    """Redact every string inside nested dicts/lists. Returns (new_obj, labels_found)."""
    if isinstance(obj, str):
        return redact(obj)
    found = []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            rk, fk = redact(k) if isinstance(k, str) else (k, [])
            out[rk], f = redact_obj(v)
            found += fk + f
        return out, found
    if isinstance(obj, (list, tuple)):
        out = []
        for v in obj:
            r, f = redact_obj(v)
            out.append(r)
            found += f
        return out, found
    return obj, found


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def check_args(args):
    """Return a sorted list of guardrail labels triggered by any string in args."""
    hits = set()
    for s in _strings(args):
        if ENV_FILE.search(s):
            hits.add("env_file_access")
        for label, pattern in DANGER_PATTERNS:
            if pattern.search(s):
                hits.add(label)
    return sorted(hits)

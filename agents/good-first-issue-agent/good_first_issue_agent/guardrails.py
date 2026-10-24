"""Guardrails for untrusted data and model behaviour.

Everything fetched from GitHub or an error tracker is untrusted: issue titles,
bodies, comments, file contents and stack traces may contain secrets, personal
data, or text written to manipulate an AI ("ignore previous instructions...").

This module:
- masks secrets and personal data before text reaches the model or the terminal,
- truncates long text,
- wraps untrusted text in clearly marked blocks for the prompt,
- flags likely prompt-injection attempts,
- checks model output against the evidence we actually fetched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Masking -----------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)")),
    ("github-token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("google-api-key", re.compile(r"\bAQ\.[0-9A-Za-z_\-.]{30,}")),
    ("aws-access-key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai-key", re.compile(r"\bsk-(proj-|ant-)?[A-Za-z0-9_\-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("bearer-token", re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._\-]{20,}")),
    ("url-credentials", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")),
    (
        "assigned-secret",
        re.compile(r"(?i)\b(api[_-]?key|api[_-]?token|secret|password|passwd|token|access[_-]?token|auth[_-]?token)\b(\s*[:=]\s*)['\"]?[^\s'\",]{6,}"),
    ),
]

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")


def redact(text: str, *, personal_data: bool = True) -> tuple[str, int]:
    """Mask secrets (and optionally emails / IP addresses). Returns (text, count)."""
    if not text:
        return text or "", 0
    count = 0

    def _sub(pattern: re.Pattern[str], repl, s: str) -> str:
        nonlocal count
        new, n = pattern.subn(repl, s)
        count += n
        return new

    for name, pattern in _SECRET_PATTERNS:
        if name == "url-credentials":
            text = _sub(pattern, lambda m: f"{m.group(1)}[REDACTED]@", text)
        elif name == "assigned-secret":
            text = _sub(pattern, lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
        else:
            text = _sub(pattern, f"[REDACTED:{name}]", text)
    if personal_data:
        text = _sub(_EMAIL, "[REDACTED:email]", text)
        text = _sub(_IPV4, "[REDACTED:ip]", text)
    return text, count


def truncate(text: str, max_chars: int) -> str:
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars].rstrip() + f"\n[... truncated, {len(text) - max_chars} more characters]"


def clean(text: str, max_chars: int, *, personal_data: bool = True) -> str:
    """Redact then truncate. Use on every piece of untrusted text."""
    return truncate(redact(text or "", personal_data=personal_data)[0], max_chars)


# --- Prompt injection --------------------------------------------------------

_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any |the )?(previous|prior|above|system) (instructions|prompts?|rules)",
    r"forget (all |your )?(previous |prior )?instructions",
    r"you are now (a|an|in) ",
    r"new (system )?instructions?:",
    r"\bsystem prompt\b",
    r"(reveal|print|show|output|send|leak)\b.{0,40}\b(api[_ ]?key|token|secret|password|credentials|env(ironment)? var)",
    r"\bdeveloper mode\b",
    r"\bjailbreak\b",
    r"</?\s*(system|assistant|untrusted_data)\s*>",
    r"(run|execute)\b.{0,30}\b(rm -rf|curl .*\|\s*(ba)?sh|powershell)",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)


def detect_injection(text: str) -> list[str]:
    """Return phrases that look like attempts to instruct an AI. Empty if none."""
    if not text:
        return []
    found = []
    for m in _INJECTION_RE.finditer(text):
        phrase = m.group(0).strip()
        if phrase and phrase.lower() not in (f.lower() for f in found):
            found.append(phrase[:60])
        if len(found) >= 3:
            break
    return found


def wrap_untrusted(source: str, text: str) -> str:
    """Wrap untrusted text in a marked block. Any tags inside are neutralized so
    the content cannot close the block early."""
    safe = re.sub(r"<\s*/?\s*untrusted_data[^>]*>", "[tag removed]", text or "", flags=re.IGNORECASE)
    return f'<untrusted_data source="{source}">\n{safe}\n</untrusted_data>'


# --- Evidence extraction and output checking ---------------------------------

_PATH_RE = re.compile(
    r"(?<![\w.:-])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8}|[\w-]+\.(?:py|pyx|pxd|pyi|js|mjs|cjs|ts|tsx|jsx|vue|svelte|go|rs|java|kt|kts|scala|swift|rb|php|cs|cpp|cc|c|h|hpp|sql|md|rst|toml|yaml|yml|json|cfg|ini|html|css|scss|sh))(?![\w/])"
)
_URLISH = re.compile(r"https?://\S+")
_BACKSLASH_SEP = re.compile(r"(?<=[\w.~:])\\(?=[\w.])")  # Windows paths: a\b\c.py -> a/b/c.py
_INSTALL_PREFIX = re.compile(r"^.*?(?:site-packages|dist-packages|node_modules)/")
# Technology names that look like file names.
_NOT_PATHS = {
    "node.js", "vue.js", "next.js", "nuxt.js", "express.js", "three.js", "d3.js",
    "chart.js", "react.js", "angular.js", "ember.js", "backbone.js", "nest.js", "deno.js",
}


def extract_paths(text: str, limit: int = 15) -> list[str]:
    """File paths that literally appear in text (URLs are ignored)."""
    if not text:
        return []
    text = _BACKSLASH_SEP.sub("/", _URLISH.sub(" ", text))
    out: list[str] = []
    for m in _PATH_RE.finditer(text):
        p = m.group(1)[2:] if m.group(1).startswith("./") else m.group(1)
        # Absolute or installed paths: keep the part inside the package, e.g.
        # /home/u/.venv/lib/python3.12/site-packages/pandas/core/frame.py -> pandas/core/frame.py
        p = _INSTALL_PREFIX.sub("", p)
        if p.lower() in _NOT_PATHS:
            continue
        if p not in out:
            out.append(p)
        if len(out) >= limit:
            break
    return out


@dataclass
class OutputCheck:
    text: str
    warnings: list[str] = field(default_factory=list)


_ISSUE_REF = re.compile(r"(?<![\w&/])#(\d{1,7})\b")


def check_model_output(
    text: str,
    *,
    known_issue_ids: set[str],
    evidence_paths: set[str],
    check_issue_refs: bool = True,
) -> OutputCheck:
    """Validate model text against fetched evidence.

    - Issue references (#123) not in the fetched set are marked [unverified].
    - File paths not found in issue text, stack traces or tool results are marked [unverified].
    - Secrets are masked in case the model echoed one.
    """
    warnings: list[str] = []
    text, n = redact(text or "", personal_data=False)
    if n:
        warnings.append(f"Masked {n} secret-like value(s) in the AI output.")

    if check_issue_refs:
        bad_refs: list[str] = []

        def _ref(m: re.Match[str]) -> str:
            if m.group(1) in known_issue_ids:
                return m.group(0)
            if m.group(1) not in bad_refs:
                bad_refs.append(m.group(1))
            return f"{m.group(0)} [unverified]"

        text = _ISSUE_REF.sub(_ref, text)
        if bad_refs:
            warnings.append(
                "AI mentioned issue number(s) that were not in the fetched data: "
                + ", ".join("#" + r for r in bad_refs)
            )

    evidence_lower = {p.lower() for p in evidence_paths}
    evidence_names = {p.rsplit("/", 1)[-1].lower() for p in evidence_paths}
    bad_paths: list[str] = []
    for path in extract_paths(text, limit=50):
        low = path.lower()
        supported = low in evidence_lower or any(e.endswith("/" + low) or low.endswith("/" + e) for e in evidence_lower)
        if not supported and "/" not in path and low in evidence_names:
            supported = True
        if not supported and path not in bad_paths:
            bad_paths.append(path)
    for path in bad_paths:
        text = re.sub(rf"(?<![\w/.-]){re.escape(path)}(?![\w/])(?! \[unverified\])", f"{path} [unverified]", text)
    if bad_paths:
        warnings.append(
            "AI mentioned file path(s) not found in the fetched evidence (marked [unverified]): "
            + ", ".join(bad_paths[:8])
        )
    return OutputCheck(text=text, warnings=warnings)


# --- Input validation ----------------------------------------------------------

SLUG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,99}$")
SAFE_REPO_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[\w.\-/ ]{0,200}$")


def is_safe_repo_path(path: str) -> bool:
    """A relative repository path with no '..' segments, absolute paths, or odd characters."""
    return bool(SAFE_REPO_PATH_RE.match(path or ""))

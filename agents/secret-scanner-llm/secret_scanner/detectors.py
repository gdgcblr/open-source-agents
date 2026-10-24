"""Stage 1: deterministic detection (regex for known formats + entropy)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .redaction import char_classes, is_uuid, shannon_entropy

_KEYWORDS = (
    r"(?:password|passwd|pwd|passphrase|secret|token|api[_-]?key|apikey|access[_-]?key"
    r"|private[_-]?key|credentials?)"
)
_NAME = rf"[A-Za-z0-9_.\-]*{_KEYWORDS}[A-Za-z0-9_.\-]*"
_TEMPLATE_START = ("${", "{{", "%(", "$(", "{%", "$")


@dataclass(frozen=True)
class Rule:
    name: str
    kind: str
    pattern: re.Pattern
    group: int | str = 0
    high_confidence_format: bool = False
    severity: str = "medium"
    priority: int = 2  # lower wins on overlap
    keep: int = 0  # leading chars kept in the redacted form
    keep_whole: bool = False  # value is public marker text (PEM header)


@dataclass(frozen=True)
class Match:
    rule: Rule
    start: int
    end: int
    value: str = field(repr=False)  # RAW. Never log / serialise this.


def _c(p: str, flags: int = 0) -> re.Pattern:
    return re.compile(p, flags)


RULES: tuple[Rule, ...] = (
    # --- known formats (high confidence) --------------------------------------------------
    Rule("aws_access_key_id", "aws_access_key", _c(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[A-Z0-9]{16}\b"),
         high_confidence_format=True, severity="critical", priority=0, keep=6),
    Rule("github_token", "github_token", _c(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
         high_confidence_format=True, severity="critical", priority=0, keep=7),
    Rule("github_fine_grained_pat", "github_token", _c(r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b"),
         high_confidence_format=True, severity="critical", priority=0, keep=14),
    Rule("stripe_live_key", "stripe_key", _c(r"\b[sr]k_live_[A-Za-z0-9]{16,247}\b"),
         high_confidence_format=True, severity="critical", priority=0, keep=11),
    Rule("google_api_key", "google_api_key", _c(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
         high_confidence_format=True, severity="high", priority=0, keep=6),
    Rule("slack_token", "slack_token", _c(r"\bxox[baprs]-[A-Za-z0-9\-]{10,250}\b"),
         high_confidence_format=True, severity="high", priority=0, keep=8),
    Rule("private_key_header", "private_key",
         _c(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----"),
         high_confidence_format=True, severity="critical", priority=0, keep_whole=True),
    # --- other structured formats (not "known provider format") ------------------------------
    Rule("jwt", "jwt",
         _c(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
         severity="medium", priority=1, keep=3),
    Rule("url_credentials", "url_credentials",
         _c(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s:/@'\"<>]+:(?P<v>[^\s@/'\"<>]{3,})@"),
         group="v", severity="high", priority=1),
    Rule("shell_password_flag", "shell_password",
         _c(r"(?i)--(?:password|passwd|pass|token|secret|api-key)(?:=|\s+)['\"]?(?P<v>(?!\$)[^\s'\"]{4,})"),
         group="v", severity="high", priority=1),
    Rule("sshpass", "shell_password",
         _c(r"\bsshpass\s+-p\s*['\"]?(?P<v>(?!\$)[^\s'\"]{3,})"),
         group="v", severity="high", priority=1),
    Rule("mysql_inline_password", "shell_password",
         _c(r"\bmysql(?:dump|admin)?\b[^\n|;&]*?\s-p(?P<v>(?![\s$\-])[^\s'\"]{3,})"),
         group="v", severity="high", priority=1),
    Rule("curl_basic_auth", "shell_password",
         _c(r"\bcurl\b[^\n]*?\s(?:-u|--user)\s+['\"]?[^\s:'\"$]+:(?P<v>(?!\$)[^\s'\"]{3,})"),
         group="v", severity="high", priority=1),
    Rule("authorization_header", "bearer_token",
         _c(r"(?i)authorization['\"]?\s*[:=]?\s*['\"]?\s*(?:bearer|basic|token)\s+(?P<v>[A-Za-z0-9._~+/=\-]{12,})"),
         group="v", severity="high", priority=1),
    # --- generic assignments ---------------------------------------------------------------------
    Rule("quoted_credential_assignment", "credential_assignment",
         _c(rf"(?i)(?P<n>{_NAME})['\"]?\s*(?:=>|:=|=|:)\s*(?P<q>['\"])(?P<v>[^'\"\n]{{6,200}})(?P=q)"),
         group="v", severity="medium", priority=2),
    Rule("unquoted_credential_assignment", "credential_assignment",
         _c(rf"(?i)(?P<n>{_NAME})\s*(?:=|:)\s*(?P<v>[^\s'\"`#,;<>{{}}()\[\]$][^\s'\"`#,;()<>]{{7,}})"),
         group="v", severity="medium", priority=2),
)

_QUOTED_TOKEN = _c(r"""(?P<q>['"`])(?P<v>[A-Za-z0-9+/=_\-.]{20,200})(?P=q)""")
_HEXISH = _c(r"^[0-9a-fA-F]+$")
ENTROPY_RULE = Rule("high_entropy_string", "high_entropy_string", _QUOTED_TOKEN, group="v",
                    severity="low", priority=3)


def is_high_entropy(v: str) -> bool:
    if is_uuid(v) or v.startswith(("/", ".")) or "//" in v:
        return False
    if not re.search(r"[0-9]", v) or not re.search(r"[A-Za-z]", v):
        return False
    ent = shannon_entropy(v)
    if _HEXISH.match(v):
        return len(v) >= 32 and ent >= 3.0
    classes = char_classes(v)
    return ent >= 3.7 and (classes >= 3 or (classes >= 2 and len(v) >= 32))


def _value_ok(rule: Rule, value: str) -> bool:
    if rule.kind in ("credential_assignment",):
        if value.startswith(_TEMPLATE_START):
            return False
        if rule.name.startswith("unquoted"):
            # Require letters+digits so `token: string` / `max_tokens: 1024` don't match.
            return bool(re.search(r"[A-Za-z]", value) and re.search(r"[0-9]", value))
    if rule.kind == "url_credentials" and value.startswith(_TEMPLATE_START):
        return False
    if rule.kind == "bearer_token" and value.startswith(("{", "$")):
        return False
    return True


def find_matches(line: str) -> list[Match]:
    """All non-overlapping matches in one line, higher-priority rules winning."""
    if len(line) > 20000:  # minified blobs: skip rather than burn CPU
        return []
    cands: list[Match] = []
    for rule in RULES:
        for m in rule.pattern.finditer(line):
            g = rule.group
            val = m.group(g)
            if val is None or not _value_ok(rule, val):
                continue
            cands.append(Match(rule, m.start(g), m.end(g), val))
    for m in ENTROPY_RULE.pattern.finditer(line):
        if is_high_entropy(m.group("v")):
            cands.append(Match(ENTROPY_RULE, m.start("v"), m.end("v"), m.group("v")))
    cands.sort(key=lambda x: (x.rule.priority, x.start, -(x.end - x.start)))
    chosen: list[Match] = []
    for c in cands:
        if not any(c.start < o.end and o.start < c.end for o in chosen):
            chosen.append(c)
    chosen.sort(key=lambda x: x.start)
    return chosen

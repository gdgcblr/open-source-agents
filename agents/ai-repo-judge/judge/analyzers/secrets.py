"""Secret scanning over the current tree and every line added by the PR's commits.

A real-looking key in code or config gates the merge. In docs or test data a realistic fake can't be told
apart from a leak, so it becomes a loud, non-gating finding that asks the author to confirm.
Secrets are redacted before they leave this module, so the dashboard never republishes a key.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

from judge.models import Check, Finding
from judge.workspace import DOC_EXTS, Workspace

DIM = "security"


@dataclass(frozen=True)
class SecretRule:
    name: str
    pattern: re.Pattern[str]


# Vendor-specific formats: high confidence.
SECRET_RULES = [
    SecretRule("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
    SecretRule("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    SecretRule("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{48,}\b")),
    SecretRule("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    SecretRule("Google auth key", re.compile(r"\bAQ\.[A-Za-z0-9_-]{40,}\b")),
    SecretRule("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    SecretRule("OpenAI API key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b")),
    SecretRule("OpenRouter API key", re.compile(r"\bsk-or-v1-[a-f0-9]{48,}\b")),
    SecretRule("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b")),
    SecretRule("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    SecretRule("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    SecretRule("Stripe live key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{24,}\b")),
    SecretRule("Tavily API key", re.compile(r"\btvly-[A-Za-z0-9-]{20,}\b")),
    SecretRule("Private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
]
GENERIC_ASSIGN = re.compile(
    r"""(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|ACCESS[_-]?KEY)[A-Z0-9_]*)\s*[:=]\s*"""
    r"""(["']?)([^\s"'#,;]{16,})\2"""
)
EXAMPLE_VALUE = re.compile(r"(?i)example|fake|dummy|sample|xxxx|0{6}|123456|abcdef|placeholder|redacted|your")
PLACEHOLDER = re.compile(
    r"(?i)your|xxx|<|\$\{|changeme|example|placeholder|here|dummy|fake|sample|test|"
    r"replace|insert|getenv|environ|process\.env|todo|none|null|\*\*\*"
)
NOT_SECRET_NAME = re.compile(
    r"(?i)MODEL|URL|ENDPOINT|PATH|FILE|DIR|NAME|LIMIT|COUNT|TYPE|HEADER|MAX|MIN|SIZE|"
    r"LENGTH|ENCODING|PREFIX|FIELD|ENV|VAR|REGEX|PATTERN"
)
WORDY = re.compile(r"[A-Za-z]+(?:[-_.][A-Za-z0-9]+)+|[a-z_][a-z0-9_.]*")  # model names, identifiers, dotted paths
CONFIG_EXTS = (".env", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".toml", ".properties", ".json")
CREDENTIAL_FILES = re.compile(
    r"(^|/)(credentials\.json|token\.json|client_secret[^/]*\.json|service[-_]?account"
    r"[^/]*\.json|id_rsa[^/]*|id_ed25519[^/]*|[^/]+\.(pem|key|p12|pfx|keystore))$",
    re.I,
)
ENV_FILE = re.compile(r"(^|/)\.env(\.[^/]+)?$")
ENV_EXAMPLE = re.compile(r"(^|/)\.env\.(example|sample|template|dist)$")
ENV_VALUE = re.compile(r"^\s*[A-Z0-9_]+\s*=\s*\S")


def entropy(s: str) -> float:
    """Shannon entropy in bits per character."""
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values())


def redact(secret: str) -> str:
    return f"{secret[:4]}…({len(secret)} chars)"


def context(path: str) -> str:
    """'data' (tests/fixtures/samples/patches), 'docs' (markdown/text) or 'code' (code and config)."""
    if Workspace.is_data_file(path):
        return "data"
    return "docs" if path.lower().endswith(DOC_EXTS) else "code"


def _vendor_hits(path: str, line: str) -> Iterator[tuple[str, str]]:
    for rule in SECRET_RULES:
        for m in rule.pattern.finditer(line):
            secret = m.group(0)
            if rule.name == "Private key":
                if context(path) != "data":  # fixture keys in tests are the norm for crypto/security tools
                    yield rule.name, secret
                continue
            body = secret.split("_", 1)[-1] if "_" in secret[:5] else secret
            if not EXAMPLE_VALUE.search(secret) and entropy(body) >= 3.0:  # skips AKIA…EXAMPLE, ghp_AAAA…
                yield rule.name, secret


def _looks_random(value: str) -> bool:
    return bool(re.search(r"\d", value) and re.search(r"[A-Za-z]", value)) and entropy(value) >= 3.7


def _generic_hits(path: str, line: str) -> Iterator[tuple[str, str]]:
    """`password = "…"`-style assignments in code/config (docs and tests are almost always illustrations)."""
    if context(path) != "code":
        return
    is_config = path.lower().endswith(CONFIG_EXTS) or bool(ENV_FILE.search(path))
    for m in GENERIC_ASSIGN.finditer(line):
        name, quote, value = m.group(1), m.group(2), m.group(3)
        if (not quote and not is_config) or NOT_SECRET_NAME.search(name):
            continue
        if PLACEHOLDER.search(value) or WORDY.fullmatch(value) or not _looks_random(value):
            continue
        if not any(r.pattern.search(value) for r in SECRET_RULES):  # vendor rules already report those
            yield f"Possible secret in {name}", value


def secret_hits(path: str, line: str) -> Iterator[tuple[str, str, bool]]:
    """Yield (rule_name, secret, is_vendor) for each secret-looking token on a line."""
    for name, secret in _vendor_hits(path, line):
        yield name, secret, True
    for name, secret in _generic_hits(path, line):
        yield name, secret, False


def _finding(name: str, secret: str, vendor: bool, rel: str, line: int, text: str, commit: str | None) -> Finding:
    ctx = context(rel)
    gate = vendor and ctx == "code"
    where = "in commit history" if commit else "committed"
    if gate:
        title = f"{name} {where}"
        detail = (
            "The key was removed from the files but is still visible in an earlier commit of this PR."
            if commit
            else "Anyone can read this key in the public PR. Revoke it now; deleting the line is not enough."
        )
    elif vendor:
        title = f"{name}-shaped string in {'documentation' if ctx == 'docs' else 'test/sample data'}"
        detail = "It may be a realistic fake. If it is a real key, revoke it: it is public in this PR."
    else:
        title, detail = f"{name} {where}", "Looks like a credential assigned in code."
    fix = (
        "Use an obviously fake value (e.g. sk-test-EXAMPLE) in docs and tests."
        if vendor and not gate
        else "Revoke/rotate the key, load it from an environment variable and document it in .env.example."
    )
    return Finding(
        dimension=DIM,
        severity="critical" if gate else "high",
        gate=gate,
        title=title,
        file=rel,
        line=line,
        commit=commit,
        detail=detail,
        snippet=text.replace(secret, redact(secret)).strip()[:200],
        fix=fix,
    )


def scan(ws: Workspace) -> tuple[list[Finding], list[Check]]:
    """Secret findings plus the `no_secrets` and (for PRs) `history_clean` checks."""
    seen: set[str] = set()
    current: list[Finding] = []
    for rel in ws.files:
        for i, line in enumerate((ws.read(rel) or "").splitlines(), 1):
            for name, secret, vendor in secret_hits(rel, line):
                if secret not in seen:
                    seen.add(secret)
                    current.append(_finding(name, secret, vendor, rel, i, line, None))

    prefix = ws.project_path.rstrip("/") + "/"
    history: list[Finding] = []
    for added in ws.history:
        rel = added.path[len(prefix) :] if added.path.startswith(prefix) else "/" + added.path
        for name, secret, vendor in secret_hits(added.path, added.text):
            if secret not in seen:
                seen.add(secret)
                history.append(_finding(name, secret, vendor, rel, added.line, added.text, added.commit[:10]))

    gating = sum(f.gate for f in current)
    soft = len(current) - gating
    checks = [
        Check(
            id="no_secrets",
            dimension=DIM,
            label="No API keys or credentials in files",
            weight=4,
            status="fail" if gating else "warn" if soft else "pass",
            detail=f"{gating} live-looking key(s) in code/config, {soft} to confirm in docs/tests"
            if current
            else "No secrets detected",
            fix="Revoke the keys and move them to a git-ignored .env file."
            if gating
            else "Replace key-shaped strings in docs/tests with obviously fake values."
            if soft
            else None,
        )
    ]
    if ws.meta.state != "local":
        leaked = sum(f.gate for f in history)
        checks.append(
            Check(
                id="history_clean",
                dimension=DIM,
                label="No secrets anywhere in the PR's commit history",
                weight=2,
                status="fail" if leaked else "pass",
                detail=f"{leaked} secret(s) found in earlier commits"
                if leaked
                else f"Scanned {len(ws.history)} added lines across all commits",
                fix="Revoke the leaked keys; they remain public in git history." if leaked else None,
            )
        )
    return current + history, checks


def _env_file_finding(ws: Workspace, rel: str) -> Finding:
    values = [
        ln
        for ln in (ws.read(rel) or "").splitlines()
        if ENV_VALUE.match(ln) and not PLACEHOLDER.search(ln.split("=", 1)[1])
    ]
    return Finding(
        dimension=DIM,
        severity="critical" if values else "medium",
        gate=bool(values),
        file=rel,
        title=".env file committed" + (" with real values" if values else ""),
        detail="CONTRIBUTING.md: never commit .env files.",
        fix="Delete it from the branch, add `.env` to .gitignore and ship .env.example instead.",
    )


def _credential_file_finding(ws: Workspace, rel: str) -> Finding:
    text = ws.read(rel) or ""
    sensitive = "PRIVATE KEY" in text or '"private_key"' in text or "client_secret" in text
    return Finding(
        dimension=DIM,
        severity="critical" if sensitive else "high",
        gate=sensitive,
        file=rel,
        title="Credential file committed",
        detail="Service-account, key and token files must never be committed.",
        fix="Remove the file, revoke the credential and load it from a path in an environment variable.",
    )


def credential_files(ws: Workspace) -> tuple[list[Finding], Check]:
    """Committed .env files and credential files (service accounts, private keys, tokens)."""
    findings = []
    for rel in ws.files:
        if ENV_FILE.search(rel) and not ENV_EXAMPLE.search(rel):
            findings.append(_env_file_finding(ws, rel))
        elif CREDENTIAL_FILES.search(rel):
            findings.append(_credential_file_finding(ws, rel))
    check = Check(
        id="no_credential_files",
        dimension=DIM,
        label="No .env or credential files committed",
        weight=2,
        status="fail" if findings else "pass",
        detail=", ".join(f.file or "" for f in findings) if findings else "None found",
    )
    return findings, check

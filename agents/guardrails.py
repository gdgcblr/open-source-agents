"""Conservative, fail-closed boundaries for untrusted diffs and outbound data."""
from __future__ import annotations
import os
import re
from urllib.parse import urlsplit

class GuardrailError(RuntimeError):
    pass

MAX_DIFF_BYTES = 1_000_000
MAX_FILES = 80
SENSITIVE = re.compile(r"(^|/)(\.env(?:\..*)?|id_(?:rsa|ed25519)|credentials(?:\..*)?|service.account.*|.*\.(?:pem|key|p12|pfx)|\.aws/.*|\.ssh/.*)$", re.I)
SECRET = re.compile(r"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|(?i:api[_-]?key|secret|passwd|password|token|client[_-]?secret)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']|(?i:password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[A-Za-z0-9_/-]{8,}|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}")
PLACEHOLDER = re.compile(r"(?i)(your[-_ ]|example|placeholder|dummy|changeme|fake[-_ ]|test[-_ ])")

def sensitive_path(path: str) -> bool:
    return bool(SENSITIVE.search(path.replace('\\','/')))

def redact(text: str) -> str:
    text = re.sub(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[^\s\"']{8,}", r"\1=[REDACTED_SECRET]", text)
    def mask(match):
        return match.group(0) if PLACEHOLDER.search(match.group(0)) else '[REDACTED_SECRET]'
    return SECRET.sub(mask, text)

def check_diff(text: str) -> None:
    if len(text.encode('utf-8')) > MAX_DIFF_BYTES:
        raise GuardrailError('Diff exceeds maximum size (1 MB)')

def allow_remote() -> None:
    if os.getenv('ALLOW_REMOTE_CODE_SHARING', '').lower() != 'true':
        raise GuardrailError('Remote model disabled: set ALLOW_REMOTE_CODE_SHARING=true only for authorized code')

def validate_base_url(url: str, local: bool = False) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
        raise GuardrailError('Invalid model endpoint')
    if local:
        if parts.scheme != 'http' or parts.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise GuardrailError('Ollama endpoint must be HTTP loopback')
    elif parts.scheme != 'https' or parts.hostname != 'api.openai.com':
        raise GuardrailError('OpenAI endpoint must be https://api.openai.com; use Ollama for local models')
    return url.rstrip('/')

def safe_text(text: str, limit: int = 500) -> str:
    return redact(str(text)).replace('\x00', '')[:limit]

def is_sensitive_path(path: str) -> bool:
    return sensitive_path(path)

def remote_preflight(files) -> None:
    allow_remote()
    for f in files:
        if sensitive_path(f.path):
            raise GuardrailError('Remote inference blocked: sensitive file path')
        if SECRET.search(f.patch) and redact(f.patch) != f.patch:
            raise GuardrailError('Remote inference blocked: suspected credential')

def safe_note(message: str) -> str:
    return safe_text(message, 240)

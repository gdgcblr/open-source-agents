import os
import re
import json
from google import genai
from models import Finding, Severity

_PATTERNS = [
    r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|api_secret)\s*[=:]\s*["\']?[A-Za-z0-9+/\-_\.]{10,}',
    r'(?i)(password|passwd|pwd|secret)\s*[=:]\s*["\'].{4,}["\']',
    r'sk-[A-Za-z0-9]{20,}',
    r'AIza[0-9A-Za-z\-_]{35}',
    r'AKIA[0-9A-Z]{16}',
    r'(?i)bearer\s+[A-Za-z0-9\-_\.]{20,}',
    r'ghp_[A-Za-z0-9]{36}',
    r'ghs_[A-Za-z0-9]{36}',
    r'xox[baprs]-[0-9A-Za-z]{10,}',
    r'(?i)\.env\b',
    r'(?i)private[_-]?key',
    r'(?i)(token|key|secret|credential)\s*[=:]\s*["\'][A-Za-z0-9+/\-_\.]{12,}["\']',
    r'-----BEGIN\s+(RSA|EC|OPENSSH|PGP)\s+PRIVATE',
    r'(?i)(client_secret|client_id)\s*[=:]\s*["\'][A-Za-z0-9\-_]{8,}["\']',
    r'(?i)(database_url|db_password|db_url)\s*[=:]\s*["\'].+["\']',
]
_COMPILED = [re.compile(p) for p in _PATTERNS]


def _extract_suspicious_lines(diff: str) -> list[tuple[str, str]]:
    hits = []
    for i, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+"):
            continue
        for pattern in _COMPILED:
            if pattern.search(line):
                hits.append((f"line {i}", line[1:].strip()))
                break
    return hits


def run(diff: str) -> list[Finding]:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    suspicious = _extract_suspicious_lines(diff)
    if not suspicious:
        return []

    lines_text = "\n".join(f"[{ref}] {content}" for ref, content in suspicious)

    prompt = f"""You are a security expert reviewing lines from a git diff for credential and secret exposure.

Lines that matched security patterns:

{lines_text}

For each line, assess and flag it if ANY of the following are true:
1. It contains a hardcoded secret, token, password, or API key (real or fake — fake keys in test files still train bad habits and can be mistaken for real ones)
2. It contains an environment variable assignment that suggests a secret is being stored insecurely
3. It references a private key, certificate, or credential file
4. It contains a connection string or database URL with embedded credentials

Be inclusive — flag test keys, example keys, and placeholder-looking values at LOW or MEDIUM confidence. Only mark confidence > 0.8 for clearly real keys.

Respond ONLY with a JSON array. Each element:
{{
  "line_ref": "<line reference>",
  "is_real_secret": true/false,
  "type": "<e.g. AWS Access Key, OpenAI API Key, Hardcoded Password, Test Credential>",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "confidence": 0.0-1.0,
  "description": "<one sentence explanation>"
}}

Return [] only if lines are clearly unrelated to secrets (e.g. variable names without values, comments).
"""

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = response.text.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        return []

    findings = []
    for r in results:
        if not r.get("is_real_secret"):
            continue
        findings.append(Finding(
            agent="SecretsAgent",
            severity=Severity(r.get("severity", "MEDIUM")),
            title=f"Hardcoded {r.get('type', 'Secret')} detected",
            description=r.get("description", ""),
            line_ref=r.get("line_ref"),
            confidence=float(r.get("confidence", 0.7)),
        ))

    return findings

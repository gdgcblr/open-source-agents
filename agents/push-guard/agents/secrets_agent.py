import os
import re
import json
from google import genai
from models import Finding, Severity

# (pattern, label, auto_severity) — auto_severity means skip Gemini, flag directly
_PATTERNS = [
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key", Severity.CRITICAL),
    (r'sk-[A-Za-z0-9]{20,}', "OpenAI API Key", Severity.CRITICAL),
    (r'AIza[0-9A-Za-z\-_]{35}', "Google API Key", Severity.CRITICAL),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub PAT", Severity.CRITICAL),
    (r'ghs_[A-Za-z0-9]{36}', "GitHub App Token", Severity.CRITICAL),
    (r'xox[baprs]-[0-9A-Za-z\-]{10,}', "Slack Token", Severity.CRITICAL),
    (r'-----BEGIN\s+(RSA|EC|OPENSSH|PGP)\s+PRIVATE', "Private Key", Severity.CRITICAL),
    (r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*["\']?[A-Za-z0-9+/\-_\.]{16,}', "API Key/Token", Severity.HIGH),
    (r'(?i)(password|passwd|pwd|secret)\s*[:=]\s*["\'][^"\']{6,}["\']', "Hardcoded Password", Severity.HIGH),
    (r'(?i)(client_secret|client_id)\s*[:=]\s*["\'][A-Za-z0-9\-_]{8,}["\']', "OAuth Client Secret", Severity.HIGH),
    (r'(?i)(database_url|db_password|db_url|connection_string)\s*[:=]\s*["\'].+["\']', "Database Credential", Severity.HIGH),
    (r'(?i)private[_-]?key\s*[:=]', "Private Key Reference", Severity.MEDIUM),
    (r'(?i)\.env\b', ".env File Reference", Severity.LOW),
]
_COMPILED = [(re.compile(p), label, sev) for p, label, sev in _PATTERNS]

# These are so specific they don't need LLM confirmation
_AUTO_CONFIRM = {Severity.CRITICAL}


def _extract_hits(diff: str):
    hits = []
    for i, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pattern, label, sev in _COMPILED:
            if pattern.search(line):
                hits.append((f"line {i}", line[1:].strip(), label, sev))
                break
    return hits


def run(diff: str) -> list[Finding]:
    hits = _extract_hits(diff)
    if not hits:
        return []

    findings = []

    # Auto-confirm CRITICAL patterns (specific enough, no LLM needed)
    auto = [(ref, c, lbl, sev) for ref, c, lbl, sev in hits if sev in _AUTO_CONFIRM]
    for line_ref, content, label, sev in auto:
        findings.append(Finding(
            agent="SecretsAgent",
            severity=sev,
            title=f"Hardcoded {label} detected",
            description=f"A {label} was committed directly to the repository. Rotate this credential immediately.",
            line_ref=line_ref,
            confidence=0.95,
        ))

    # Send HIGH/MEDIUM/LOW to Gemini for context-aware review
    needs_review = [(ref, c, lbl, sev) for ref, c, lbl, sev in hits if sev not in _AUTO_CONFIRM]
    if needs_review:
        try:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            lines_text = "\n".join(f"[{ref}] ({lbl}) {c}" for ref, c, lbl, sev in needs_review)
            prompt = f"""You are a secrets detection expert reviewing lines from a git diff.

{lines_text}

For each line, determine if it contains a real credential, secret, or sensitive config.
Include test credentials and example values — flag them at LOW or MEDIUM. Only exclude clearly unrelated lines.

Respond with JSON array:
{{
  "line_ref": "<ref>",
  "is_secret": true/false,
  "type": "<e.g. API Key, Password, Connection String>",
  "severity": "HIGH|MEDIUM|LOW",
  "confidence": 0.4-0.95,
  "description": "<one sentence>"
}}
"""
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            results = json.loads(raw)
            for r in results:
                if not r.get("is_secret"):
                    continue
                findings.append(Finding(
                    agent="SecretsAgent",
                    severity=Severity(r.get("severity", "MEDIUM")),
                    title=f"Hardcoded {r.get('type', 'Secret')} detected",
                    description=r.get("description", ""),
                    line_ref=r.get("line_ref"),
                    confidence=float(r.get("confidence", 0.6)),
                ))
        except Exception:
            for line_ref, content, label, sev in needs_review:
                findings.append(Finding(
                    agent="SecretsAgent",
                    severity=sev,
                    title=f"Potential {label}",
                    description=f"Pattern matched for {label} in committed code.",
                    line_ref=line_ref,
                    confidence=0.6,
                ))

    return findings

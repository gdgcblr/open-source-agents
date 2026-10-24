import re
from typing import List
from ..models import FileDiff, ReviewIssue, SpecialistVerdict

SECURITY_RULES = [
    # CWE-798: Hardcoded Credentials
    (
        r"(?i)aws_access_key_id\s*=\s*['\"][A-Za-z0-9_]{16,32}['\"]",
        "AWS Access Key ID committed in code",
        "CRITICAL",
        "CWE-798: Hardcoded Credentials",
        "Secrets must never be stored in source code. Load from environment via `os.environ.get('AWS_ACCESS_KEY_ID')` or AWS IAM roles.",
        "AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')"
    ),
    (
        r"(?i)(?:api_key|apikey|secret_key|secret)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
        "Potential hardcoded secret or API key",
        "CRITICAL",
        "CWE-798: Hardcoded Credentials",
        "Extract secret to environment variables or secret manager vault.",
        "SECRET_KEY = os.environ.get('SECRET_KEY')"
    ),
    (
        r"ghp_[0-9a-zA-Z]{36}",
        "GitHub Personal Access Token detected",
        "CRITICAL",
        "CWE-798: Hardcoded Credentials",
        "Revoke and rotate this token immediately. Inject via GitHub Secrets / CI environment.",
        "GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')"
    ),
    (
        r"-----BEGIN (?:RSA )?PRIVATE KEY-----",
        "Cryptographic Private Key committed in repository",
        "CRITICAL",
        "CWE-312: Cleartext Storage of Sensitive Information",
        "Never commit private keys into version control. Store in KeyVault/Secret Manager.",
        None
    ),
    # CWE-89: SQL Injection
    (
        r"(?i)(?:(?:cursor|db|connection)\.execute\s*\(\s*f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE)|(?:query|sql)\s*=\s*f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE))",
        "Potential SQL injection: formatted f-string in SQL query",
        "HIGH",
        "CWE-89: SQL Injection",
        "Use parameterized SQL query binding with placeholders (?, %s, or :param) to neutralize user input injection.",
        "cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))"
    ),
    # CWE-78: Command Injection
    (
        r"(?i)subprocess\.(?:Popen|call|run|check_output)\s*\(.*?shell\s*=\s*True",
        "Command Injection Risk: subprocess executed with `shell=True`",
        "HIGH",
        "CWE-78: OS Command Injection",
        "Remove `shell=True` and pass command and arguments as a sequence: `subprocess.run(['cmd', arg1])`.",
        "subprocess.run([binary_path, user_arg], check=True)"
    ),
    # CWE-95: Dangerous Code Execution
    (
        r"(?i)\b(?:eval|exec)\s*\(",
        "Dangerous dynamic code execution (`eval`/`exec`)",
        "HIGH",
        "CWE-95: Improper Neutralization of Directives in Dynamically Evaluated Code",
        "Avoid `eval()` or `exec()`. Use `ast.literal_eval()` or structured JSON/schema parsers.",
        "import ast\nresult = ast.literal_eval(safe_string)"
    ),
    # CWE-502: Insecure Deserialization
    (
        r"(?i)\bpickle\.loads?\s*\(",
        "Insecure Deserialization: untrusted `pickle` usage",
        "HIGH",
        "CWE-502: Deserialization of Untrusted Data",
        "Pickle is insecure for external data. Use JSON, Protocol Buffers, or safe serialization.",
        "import json\ndata = json.loads(payload)"
    ),
    # CWE-295: Disabled TLS Verification
    (
        r"(?i)verify\s*=\s*False",
        "TLS Certificate Verification Explicitly Disabled",
        "HIGH",
        "CWE-295: Improper Certificate Validation",
        "Enforce TLS validation (`verify=True`) to prevent Man-in-the-Middle (MITM) attacks.",
        "response = requests.get(url, verify=True)"
    ),
]


class SecurityAuditorAgent:
    """Specialist Agent focusing on OWASP Top 10, CWE security vulnerabilities, and secrets."""

    def __init__(self, name: str = "Security & Vulnerability Auditor"):
        self.name = name

    def evaluate(self, diffs: List[FileDiff]) -> SpecialistVerdict:
        findings: List[ReviewIssue] = []

        for f in diffs:
            for cl in f.changed_lines:
                if cl.line_type != "+":
                    continue
                content = cl.content

                for pattern, title, severity, cwe, fix_desc, replacement in SECURITY_RULES:
                    if re.search(pattern, content):
                        findings.append(ReviewIssue(
                            file=f.filename,
                            line=cl.line_number,
                            severity=severity,
                            category="SECURITY",
                            title=title,
                            description=f"Security audit matched {cwe} on line {cl.line_number}: {fix_desc}",
                            suggestion=fix_desc,
                            cwe_id=cwe,
                            suggested_replacement=replacement
                        ))

        # Calculate security score
        score = 100
        for issue in findings:
            if issue.severity == "CRITICAL":
                score -= 40
            elif issue.severity == "HIGH":
                score -= 20
            elif issue.severity == "MEDIUM":
                score -= 10
            elif issue.severity == "LOW":
                score -= 5
        score = max(0, score)

        if score < 60:
            status = "FAILED"
            summary = f"Detected {len(findings)} critical or high security issue(s). Immediate blocking remediation required."
        elif score < 85:
            status = "WARNING"
            summary = f"Found {len(findings)} security observation(s) requiring attention before merge."
        else:
            status = "PASSED"
            summary = "No major OWASP/CWE vulnerabilities or hardcoded secrets detected."

        return SpecialistVerdict(
            agent_name=self.name,
            score=score,
            status=status,
            summary=summary,
            findings=findings
        )

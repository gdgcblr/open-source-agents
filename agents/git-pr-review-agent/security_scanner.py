"""Deterministic pre-LLM security and secret-leak scanner."""

import re
from typing import List, Tuple
from models import ReviewIssue, ReviewSeverity, ReviewCategory

# Regex patterns for common secret leaks
SECRET_PATTERNS = [
    (
        r"AIzaSy[A-Za-z0-9_-]{33}",
        "Google API / Gemini Secret Key",
        ReviewSeverity.CRITICAL,
        "Remove this API key immediately! Use environment variables or a secret manager."
    ),
    (
        r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}",
        "GitHub Personal Access Token",
        ReviewSeverity.CRITICAL,
        "Revoke and rotate this GitHub token immediately."
    ),
    (
        r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}",
        "OpenAI API Secret Key",
        ReviewSeverity.CRITICAL,
        "Revoke this OpenAI key and load it from environment variables instead."
    ),
    (
        r"AKIA[0-9A-Z]{16}",
        "AWS Access Key ID",
        ReviewSeverity.CRITICAL,
        "Do not commit AWS keys. Use IAM roles or AWS CLI profiles."
    ),
    (
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "Private Cryptographic Key",
        ReviewSeverity.CRITICAL,
        "Private keys should never be committed to source control."
    ),
    (
        r"xox[baprs]-[0-9a-zA-Z-]{24,}",
        "Slack Token",
        ReviewSeverity.CRITICAL,
        "Revoke the Slack credential and store in secret management."
    ),
    (
        r"sk_live_[0-9a-zA-Z]{24,}",
        "Stripe Live API Key",
        ReviewSeverity.CRITICAL,
        "Stripe live keys must never be committed to version control."
    ),
    (
        r"(?:password|passwd|secret|api_key|token)\s*=\s*['\"][A-Za-z0-9@#$%^&+=_-]{8,}['\"]",
        "Hardcoded Credential / Secret Assignment",
        ReviewSeverity.WARNING,
        "Avoid assigning hardcoded secrets directly in source code. Use os.getenv() or a .env file."
    )
]

# Regex patterns for insecure coding anti-patterns (Python/JS)
CODE_SMELL_PATTERNS = [
    (
        r"\beval\s*\(",
        "Arbitrary Code Execution via eval()",
        ReviewSeverity.CRITICAL,
        "eval() allows arbitrary code execution. Refactor to use safe parsing (e.g., ast.literal_eval or json.loads)."
    ),
    (
        r"\bexec\s*\(",
        "Arbitrary Code Execution via exec()",
        ReviewSeverity.CRITICAL,
        "Avoid exec() as it can execute malicious code. Use explicit dispatch maps or static functions."
    ),
    (
        r"subprocess\.(?:Popen|run|call)\s*\(.*shell\s*=\s*True",
        "Command Injection Risk (shell=True)",
        ReviewSeverity.WARNING,
        "subprocess with shell=True is susceptible to command injection. Pass command arguments as a list without shell=True."
    ),
    (
        r"verify\s*=\s*False",
        "Disabled SSL/TLS Certificate Verification",
        ReviewSeverity.WARNING,
        "Disabling SSL verification leaves connections vulnerable to Man-In-The-Middle (MITM) attacks."
    ),
    (
        r"cursor\.execute\s*\(\s*f[\"'].*\{.*\}[\"']",
        "Potential SQL Injection via Formatted String",
        ReviewSeverity.CRITICAL,
        "Use parameterized SQL queries (? or %s) instead of Python f-strings to prevent SQL injection."
    )
]


def scan_diff_for_security_issues(diff_text: str) -> List[ReviewIssue]:
    """
    Scans added diff lines for known secrets and security vulnerabilities.
    """
    if not diff_text:
        return []

    issues: List[ReviewIssue] = []
    current_file = "unknown"
    current_line_no = 0

    lines = diff_text.split("\n")

    for line in lines:
        if line.startswith("diff --git "):
            match = re.search(r"diff --git a/.*? b/(.*)$", line)
            current_file = match.group(1) if match else "unknown"
            current_line_no = 0

            # Check if an actual .env file is being tracked
            if current_file.endswith(".env") or current_file == ".env":
                issues.append(
                    ReviewIssue(
                        file_path=current_file,
                        line_number=1,
                        severity=ReviewSeverity.CRITICAL,
                        category=ReviewCategory.SECURITY,
                        title="Committed .env File Detected",
                        description=f"A dotenv file '{current_file}' is being tracked in git, which frequently causes catastrophic secret leaks.",
                        suggestion="Add this file to .gitignore, remove it from git cache with 'git rm --cached', and use a sanitized .env.example instead."
                    )
                )

        elif line.startswith("@@"):
            # Parse hunk line numbers (e.g. @@ -1,4 +10,6 @@)
            hunk_match = re.search(r"\+(\d+)", line)
            if hunk_match:
                current_line_no = int(hunk_match.group(1)) - 1

        elif line.startswith("+") and not line.startswith("+++"):
            current_line_no += 1
            added_content = line[1:].strip()

            # Skip comments or markdown documentation links
            if added_content.startswith("# Example:") or added_content.startswith("// Example:"):
                continue

            # 1. Scan for hardcoded secrets
            for pattern, title, severity, suggestion in SECRET_PATTERNS:
                if re.search(pattern, added_content, re.IGNORECASE):
                    issues.append(
                        ReviewIssue(
                            file_path=current_file,
                            line_number=current_line_no,
                            severity=severity,
                            category=ReviewCategory.SECURITY,
                            title=title,
                            description=f"Potential secret detected on line {current_line_no} of {current_file}.",
                            suggestion=suggestion
                        )
                    )

            # 2. Scan for dangerous code patterns
            for pattern, title, severity, suggestion in CODE_SMELL_PATTERNS:
                if re.search(pattern, added_content):
                    issues.append(
                        ReviewIssue(
                            file_path=current_file,
                            line_number=current_line_no,
                            severity=severity,
                            category=ReviewCategory.SECURITY,
                            title=title,
                            description=f"Dangerous security anti-pattern found: {added_content[:80]}",
                            suggestion=suggestion
                        )
                    )

        elif not line.startswith("-"):
            current_line_no += 1

    return issues

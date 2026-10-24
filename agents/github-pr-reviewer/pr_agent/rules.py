import re
from typing import List, Optional
from .models import FileDiff, ReviewIssue, TriageResult


SECRET_PATTERNS = [
    (r"(?i)aws_access_key_id\s*=\s*['\"][A-Za-z0-9_]{16,32}['\"]", "AWS Access Key ID committed in code", "CRITICAL"),
    (r"(?i)(?:api_key|apikey|secret_key|secret)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "Potential hardcoded secret or API key", "CRITICAL"),
    (r"ghp_[0-9a-zA-Z]{36}", "GitHub Personal Access Token detected", "CRITICAL"),
    (r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "Private cryptographic key detected in diff", "CRITICAL"),
]

SECURITY_PATTERNS = [
    (r"(?i)(?:(?:cursor|db|connection)\.execute\s*\(\s*f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE)|(?:query|sql)\s*=\s*f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE))", 
     "Potential SQL injection: raw formatted string in SQL query", "HIGH",
     "Use parameterized queries with placeholder syntax (e.g. `cursor.execute('SELECT ... WHERE user = ?', (username,))`)."),
    (r"(?i)subprocess\.(?:Popen|call|run)\s*\(.*?shell\s*=\s*True", 
     "Potential Command Injection: `shell=True` used in subprocess", "HIGH",
     "Avoid `shell=True`. Pass commands as lists of arguments directly: `subprocess.run(['cmd', arg1])`."),
    (r"(?i)\b(?:eval|exec)\s*\(", 
     "Dangerous execution: dynamic `eval()` or `exec()` usage", "HIGH",
     "Avoid `eval()` or `exec()`. Use safe parsing libraries such as `ast.literal_eval` or typed schemas."),
    (r"(?i)verify\s*=\s*False", 
     "Insecure TLS: SSL certificate verification explicitly disabled (`verify=False`)", "HIGH",
     "Ensure TLS certificate verification is enabled in production environments."),
]

CODE_SMELL_PATTERNS = [
    (r"(?i)\bprint\s*\(\s*f?[\"'].*?debug", "Debug print statement left in code", "LOW",
     "Use standard logging library (`logger.debug(...)`) instead of print statements."),
    (r"(?i)console\.log\s*\(", "JavaScript console.log statement found in production code", "LOW",
     "Remove debugging console logs before merging."),
    (r"(?i)#\s*TODO[:\s]", "Unresolved TODO item added in diff", "INFO",
     "Ensure this TODO is tracked in a corresponding issue or resolved prior to merge."),
]


def run_heuristic_checks(diffs: List[FileDiff]) -> List[ReviewIssue]:
    """Scan diff additions using regex patterns for security and code smell heuristics."""
    issues: List[ReviewIssue] = []

    for file_diff in diffs:
        for cl in file_diff.changed_lines:
            if cl.line_type != "+":
                continue

            content = cl.content

            # 1. Secret patterns
            for pattern, title, severity in SECRET_PATTERNS:
                if re.search(pattern, content):
                    issues.append(ReviewIssue(
                        file=file_diff.filename,
                        line=cl.line_number,
                        severity=severity,
                        category="SECURITY",
                        title=title,
                        description=f"Hardcoded sensitive data pattern matched on line {cl.line_number}.",
                        suggestion="Remove secret and load it from environment variables (`os.environ.get(...)`)."
                    ))

            # 2. Security patterns
            for pattern, title, severity, fix in SECURITY_PATTERNS:
                if re.search(pattern, content):
                    issues.append(ReviewIssue(
                        file=file_diff.filename,
                        line=cl.line_number,
                        severity=severity,
                        category="SECURITY",
                        title=title,
                        description=f"Identified risky programming construct on line {cl.line_number}.",
                        suggestion=fix
                    ))

            # 3. Code smell patterns
            for pattern, title, severity, fix in CODE_SMELL_PATTERNS:
                if re.search(pattern, content):
                    issues.append(ReviewIssue(
                        file=file_diff.filename,
                        line=cl.line_number,
                        severity=severity,
                        category="CODE_SMELL",
                        title=title,
                        description=f"Code quality flag on line {cl.line_number}.",
                        suggestion=fix
                    ))

    return issues


def calculate_triage(diffs: List[FileDiff], issues: List[ReviewIssue], title: Optional[str] = None) -> TriageResult:
    """Analyze changes to compute PR size, classification, and risk tier."""
    total_additions = sum(d.additions for d in diffs)
    total_deletions = sum(d.deletions for d in diffs)
    total_files = len(diffs)
    total_changes = total_additions + total_deletions

    # Size tier
    if total_changes <= 25:
        size_tier = "XS"
    elif total_changes <= 100:
        size_tier = "S"
    elif total_changes <= 300:
        size_tier = "M"
    elif total_changes <= 800:
        size_tier = "L"
    else:
        size_tier = "XL"

    # PR type detection
    filenames = [d.filename.lower() for d in diffs]
    all_content = " ".join(" ".join(cl.content for cl in d.changed_lines) for d in diffs).lower()
    title_lower = (title or "").lower()

    if any(issue.severity == "CRITICAL" for issue in issues):
        pr_type = "Security Fix"
    elif all(f.endswith(".md") or "doc" in f for f in filenames):
        pr_type = "Documentation"
    elif all("test" in f or f.startswith("tests/") for f in filenames):
        pr_type = "Test Suite"
    elif "fix" in title_lower or "bug" in title_lower or "fix" in all_content or "bug" in all_content or any("fix" in f for f in filenames):
        pr_type = "Bug Fix"
    elif total_deletions > total_additions * 1.5:
        pr_type = "Refactor / Cleanup"
    else:
        pr_type = "Feature / Enhancement"

    # Risk assessment
    has_critical = any(i.severity == "CRITICAL" for i in issues)
    has_high = any(i.severity == "HIGH" for i in issues)
    critical_files = any(any(keyword in f for keyword in ["auth", "security", "token", "payment", "crypto"]) for f in filenames)

    if has_critical:
        risk_level = "Critical"
        summary = "CRITICAL security issues found! Hardcoded credentials or critical flaws require immediate remediation."
    elif has_high or (critical_files and size_tier in ["L", "XL"]):
        risk_level = "High"
        summary = "High risk changes identified affecting sensitive modules or containing security anti-patterns."
    elif size_tier in ["M", "L"] or critical_files:
        risk_level = "Medium"
        summary = "Moderate change volume or sensitive file modification. Thorough peer review recommended."
    else:
        risk_level = "Low"
        summary = "Low-risk patch with contained changes and no severe heuristic findings."

    return TriageResult(
        pr_type=pr_type,
        size_tier=size_tier,
        risk_level=risk_level,
        total_additions=total_additions,
        total_deletions=total_deletions,
        total_files=total_files,
        summary=summary
    )

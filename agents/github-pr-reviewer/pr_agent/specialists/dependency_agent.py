import re
from typing import List
from ..models import FileDiff, ReviewIssue, SpecialistVerdict

# Database of notable known vulnerable package versions (CVE & Advisory rules)
KNOWN_VULNERABLE_PACKAGES = [
    (
        r"(?i)urllib3\s*==\s*1\.(?:[0-9]|1[0-9]|2[0-5])(?:\.|$)",
        "Vulnerable urllib3 version (<1.26.5)",
        "HIGH",
        "CVE-2021-33503: ReDoS in urllib3",
        "Upgrade urllib3 to >= 1.26.5 or >= 2.0.0."
    ),
    (
        r"(?i)requests\s*==\s*2\.(?:[0-9]|1[0-9])(?:\.|$)",
        "Vulnerable requests version (<2.20.0)",
        "HIGH",
        "CVE-2018-18074: Authorization header leak on cross-domain redirect",
        "Upgrade requests to >= 2.31.0."
    ),
    (
        r"(?i)pyyaml\s*==\s*[1-4]\.|pyyaml\s*==\s*5\.[0-3](?:\.|$)",
        "Vulnerable PyYAML version (<5.4)",
        "CRITICAL",
        "CVE-2020-14343: Arbitrary code execution in PyYAML",
        "Upgrade pyyaml to >= 6.0.1 and ensure safe_load() is used."
    ),
    (
        r"(?i)jinja2\s*==\s*[1-2]\.|jinja2\s*==\s*3\.0\.|jinja2\s*==\s*3\.1\.[0-2](?:\.|$)",
        "Vulnerable Jinja2 version (<3.1.3)",
        "HIGH",
        "CVE-2024-22195: Cross-site scripting (XSS) via xmlattr filter",
        "Upgrade Jinja2 to >= 3.1.3."
    ),
    (
        r"(?i)flask\s*==\s*[0-1]\.|flask\s*==\s*2\.[0-1]\.|flask\s*==\s*2\.2\.[0-4](?:\.|$)",
        "Vulnerable Flask version (<2.2.5)",
        "HIGH",
        "CVE-2023-30861: Cookie secret key leak in Flask session handling",
        "Upgrade Flask to >= 3.0.0."
    ),
]


class DependencyAuditorAgent:
    """Specialist Agent that performs Software Composition Analysis (SCA) on manifests."""

    def __init__(self, name: str = "Software Composition & Dependency Auditor"):
        self.name = name

    def evaluate(self, diffs: List[FileDiff]) -> SpecialistVerdict:
        findings: List[ReviewIssue] = []
        manifest_files = ("requirements.txt", "package.json", "pyproject.toml", "pipfile")

        for f in diffs:
            if not any(f.filename.lower().endswith(m) for m in manifest_files):
                continue

            for cl in f.changed_lines:
                if cl.line_type != "+":
                    continue
                content = cl.content.strip()

                for pattern, title, severity, cwe_cve, fix in KNOWN_VULNERABLE_PACKAGES:
                    if re.search(pattern, content):
                        findings.append(ReviewIssue(
                            file=f.filename,
                            line=cl.line_number,
                            severity=severity,
                            category="SECURITY",
                            title=title,
                            description=f"Dependency advisory matched {cwe_cve} on line {cl.line_number}: {content}",
                            suggestion=fix,
                            cwe_id=cwe_cve
                        ))

        score = 100
        for issue in findings:
            if issue.severity == "CRITICAL":
                score -= 35
            elif issue.severity == "HIGH":
                score -= 20
        score = max(0, score)

        if score < 70:
            status = "FAILED"
            summary = f"Flagged {len(findings)} vulnerable or outdated package dependencies with known CVEs."
        else:
            status = "PASSED"
            summary = "No vulnerable dependency specifications identified in package manifests."

        return SpecialistVerdict(
            agent_name=self.name,
            score=score,
            status=status,
            summary=summary,
            findings=findings
        )

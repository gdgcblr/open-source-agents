"""Static rule scanner for instant vulnerability and secrets detection."""

from __future__ import annotations
import re
from dataclasses import dataclass
from .diff_parser import FileDiff


@dataclass
class Finding:
    category: str  # 'SECURITY', 'QUALITY', 'DEPENDENCY', 'COMPLIANCE'
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'
    file: str
    line: int | None
    title: str
    description: str
    suggested_fix: str = ""
    snippet: str = ""


# Regular expressions for secrets and credentials
SECRET_PATTERNS = [
    (
        "AWS Access Key ID",
        re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
        "CRITICAL",
        "Revoke key immediately and use AWS IAM roles or environment variables.",
    ),
    (
        "GitHub Personal Access Token",
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
        "CRITICAL",
        "Revoke token immediately and use GitHub Secrets / environment variables.",
    ),
    (
        "Private Cryptographic Key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        "CRITICAL",
        "Remove private key from source control immediately.",
    ),
    (
        "Hardcoded Generic Secret / API Key",
        re.compile(
            r"""(?i)(?:api_key|secret_key|auth_token|access_token|password|passwd|client_secret)\s*[:=]\s*["']([A-Za-z0-9_\-\.]{16,})["']"""
        ),
        "HIGH",
        "Extract secret to environment variables (.env) or a secret manager.",
    ),
    (
        "JSON Web Token (JWT)",
        re.compile(r"ey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "HIGH",
        "Do not commit active JWT credentials into version control.",
    ),
]

# Regular expressions for dangerous code execution and security antipatterns
CODE_SAFETY_PATTERNS = [
    (
        "Arbitrary Code Execution (eval/exec)",
        re.compile(r"\b(eval|exec)\s*\("),
        "HIGH",
        "Avoid dynamic evaluation of code. Use explicit parsing (e.g. ast.literal_eval or json.loads).",
    ),
    (
        "Insecure Subprocess (shell=True)",
        re.compile(r"\bsubprocess\.\w+\(.*shell\s*=\s*True"),
        "HIGH",
        "Pass arguments as a list without shell=True to prevent shell injection.",
    ),
    (
        "Dangerous System Call (os.system)",
        re.compile(r"\bos\.system\s*\("),
        "MEDIUM",
        "Use subprocess.run with arguments passed as an array instead of os.system.",
    ),
    (
        "Insecure Deserialization (pickle.loads)",
        re.compile(r"\bpickle\.loads\s*\("),
        "HIGH",
        "Pickle is insecure for untrusted inputs; use JSON or Protocol Buffers.",
    ),
    (
        "Potential SQL Injection (String Interpolation)",
        re.compile(
            r"""(?i)(?:f["'].*SELECT\s+.*FROM|["'].*SELECT\s+.*FROM.*%\s*\w+|format\(.*SELECT)"""
        ),
        "HIGH",
        "Use parameterized queries or ORM query builders to prevent SQL injection.",
    ),
]


class RulesScanner:
    """Heuristic scanner for diff changes."""

    def scan_files(self, files: list[FileDiff]) -> list[Finding]:
        findings: list[Finding] = []

        for f in files:
            is_doc = f.filename.endswith((".md", ".rst", ".txt"))
            is_sample_fixture = (
                "sample_diffs/" in f.filename
                or f.filename.startswith("sample_diffs/")
                or f.filename.endswith((".diff", ".patch"))
            )
            is_test_file = (
                "/tests/" in f.filename
                or f.filename.startswith("tests/")
                or "test_" in f.filename.split("/")[-1]
            )

            # Skip code safety rules and dummy secrets on documentation, test suites, and sample fixtures
            skip_code_safety = is_doc or is_sample_fixture or is_test_file
            skip_secrets = is_doc or is_sample_fixture or is_test_file

            # Check added lines
            for line_no, content in f.added_lines():
                stripped = content.strip()
                lower_content = content.lower()
                # Skip comments that document placeholders
                if (
                    stripped.startswith(("#", "//", "/*", "*"))
                    and any(k in lower_content for k in ("example", "placeholder", "your_", "<your"))
                ) or "your_api_key_here" in lower_content:
                    continue

                # 1. Scan for secrets (skip test fixtures and docs with dummy tokens)
                if not skip_secrets:
                    for title, pattern, severity, fix in SECRET_PATTERNS:
                        match = pattern.search(content)
                        if match:
                            findings.append(
                                Finding(
                                    category="SECURITY",
                                    severity=severity,
                                    file=f.filename,
                                    line=line_no,
                                    title=title,
                                    description=f"Found potential secret pattern in added code: `{match.group(0)[:6]}...`",
                                    suggested_fix=fix,
                                    snippet=stripped[:120],
                                )
                            )

                # 2. Scan for dangerous code patterns (only on executable production code, not docs or test suites)
                if not skip_code_safety:
                    for title, pattern, severity, fix in CODE_SAFETY_PATTERNS:
                        if pattern.search(content):
                            findings.append(
                                Finding(
                                    category="SECURITY",
                                    severity=severity,
                                    file=f.filename,
                                    line=line_no,
                                    title=title,
                                    description=f"Potential vulnerability: {title}",
                                    suggested_fix=fix,
                                    snippet=stripped[:120],
                                )
                            )

            # 3. Check for dependency file changes (only on real package manifests, not sample diffs or docs)
            if not is_sample_fixture and not is_doc:
                base_name = f.filename.split("/")[-1]
                if base_name in ("requirements.txt", "package.json"):
                    for line_no, content in f.added_lines():
                        cleaned = content.strip()
                        if (
                            cleaned
                            and not cleaned.startswith("#")
                            and not cleaned.startswith("{")
                            and not cleaned.startswith("}")
                            and not cleaned.startswith('"')
                        ):
                            findings.append(
                                Finding(
                                    category="DEPENDENCY",
                                    severity="INFO",
                                    file=f.filename,
                                    line=line_no,
                                    title="Dependency Added / Modified",
                                    description=f"New dependency registered: `{cleaned}`. Verify provenance and typosquatting safety.",
                                    suggested_fix="Ensure the package name is authentic and version is pinned.",
                                    snippet=cleaned,
                                )
                            )

        return findings

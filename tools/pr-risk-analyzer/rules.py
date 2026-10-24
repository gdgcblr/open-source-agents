import re
from pathlib import PurePosixPath

from models import FileChange, Finding


# Deliberately heuristic: these patterns are review signals, not proof
# that a value is a valid or active credential.
SECRET_PATTERNS = [
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "credential-assignment",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|access[_-]?token|auth[_-]?token|
            client[_-]?secret|password|passwd|secret[_-]?key)\b
            \s*[:=]\s*
            ["']?([^\s"'`,;]{6,})
            """
        ),
    ),
    (
        "bearer-token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    (
        "connection-string",
        re.compile(
            r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://"
            r"[^/\s:@]+:[^@\s]+@"
        ),
    ),
]

PLACEHOLDER_VALUES = {
    "changeme",
    "change_me",
    "example",
    "placeholder",
    "your_api_key",
    "your_token",
    "your_password",
    "replace_me",
    "redacted",
    "dummy",
    "test",
    "none",
    "null",
}


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    return (
        normalized in PLACEHOLDER_VALUES
        or normalized.startswith("your_")
        or normalized.startswith("<")
        or normalized.endswith("_here")
    )


def _redact(line: str) -> str:
    """Return safe, shortened evidence without exposing likely secrets."""
    redacted = line

    for _, pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)

    # Also avoid printing long token-like strings in evidence.
    redacted = re.sub(
        r"\b[A-Za-z0-9_+/=-]{32,}\b",
        "[REDACTED]",
        redacted,
    )
    return redacted[:200]


def _is_secret_like_assignment(line: str, pattern_name: str) -> bool:
    """Reject obvious code expressions and placeholder assignments."""
    if pattern_name != "credential-assignment":
        return True

    match = re.search(
        r"""(?ix)
        \b(?:api[_-]?key|access[_-]?token|auth[_-]?token|
        client[_-]?secret|password|passwd|secret[_-]?key)\b
        \s*[:=]\s*
        (.+)
        """,
        line,
    )

    if not match:
        return True

    value = match.group(1).strip().rstrip(",;")

    # Function calls, variable references and other code expressions
    # are not literal credentials.
    if re.match(r"^[A-Za-z_]\w*\s*\(", value):
        return False

    if re.match(
        r"^(?:None|True|False|null|undefined)\b",
        value,
        re.IGNORECASE,
    ):
        return False

    if value.startswith(("os.environ", "os.getenv", "getenv", "config.")):
        return False

    return True

def detect_secrets(files: list[FileChange]) -> list[Finding]:
    findings: list[Finding] = []

    for file_change in files:
        for line in file_change.added_lines:
            for pattern_name, pattern in SECRET_PATTERNS:
                match = pattern.search(line.content)
                if not match:
                    continue

                if not _is_secret_like_assignment(line.content, pattern_name):
                    continue

                candidate = match.group(1) if match.lastindex else match.group(0)
                if _looks_like_placeholder(candidate):
                    continue

                findings.append(
                    Finding(
                        rule_id="SEC001",
                        title="Potential hard-coded credential",
                        severity="high",
                        message=(
                            f"Added code matches the '{pattern_name}' "
                            "credential heuristic."
                        ),
                        file_path=file_change.path,
                        line_number=line.new_line_number,
                        evidence=_redact(line.content),
                        recommendation=(
                            "Verify the match. If it is a real credential, "
                            "remove it, rotate it if exposed, and use a "
                            "secret manager or environment variable."
                        ),
                        confidence="medium",
                    )
                )
                # One finding per line avoids duplicate alerts from patterns.
                break

    return findings


def detect_sensitive_paths(
    files: list[FileChange],
    sensitive_paths: list[str],
) -> list[Finding]:
    findings: list[Finding] = []
    normalized_terms = [term.lower().strip("/") for term in sensitive_paths]

    for file_change in files:
        path = file_change.path.lower()
        path_parts = set(PurePosixPath(path).parts)

        matched = [
            term for term in normalized_terms
            if term and (
                term in path_parts
                or term in path
            )
        ]
        if not matched:
            continue

        findings.append(
            Finding(
                rule_id="CODE001",
                title="Sensitive-area change",
                severity="medium",
                message=(
                    "The diff changes a path associated with "
                    f"{', '.join(matched)}."
                ),
                file_path=file_change.path,
                recommendation=(
                    "Review authorization checks, input validation, "
                    "security implications, and relevant tests."
                ),
                confidence="low",
            )
        )

    return findings


def detect_infrastructure_changes(files: list[FileChange]) -> list[Finding]:
    findings: list[Finding] = []

    infrastructure_names = {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "terraform.tf",
        "main.tf",
        "deployment.yaml",
        "deployment.yml",
        "kustomization.yaml",
    }

    for file_change in files:
        path = file_change.path.lower()
        name = PurePosixPath(path).name
        is_workflow = ".github/workflows/" in path
        is_terraform = name.endswith((".tf", ".tfvars"))
        is_kubernetes = (
            name in infrastructure_names
            or "/k8s/" in f"/{path}/"
            or "/kubernetes/" in f"/{path}/"
        )
        is_container = name in {
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        }

        if not (is_workflow or is_terraform or is_kubernetes or is_container):
            continue

        findings.append(
            Finding(
                rule_id="INFRA001",
                title="Infrastructure or deployment change",
                severity="medium",
                message=(
                    "The diff touches infrastructure, container, "
                    "or deployment configuration."
                ),
                file_path=file_change.path,
                recommendation=(
                    "Check permissions, exposed ports, privileged execution, "
                    "image versions, deployment scope, and rollback behavior "
                    "where applicable."
                ),
                confidence="medium",
            )
        )

    return findings


def detect_dependency_changes(files: list[FileChange]) -> list[Finding]:
    findings: list[Finding] = []

    dependency_names = {
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "pipfile",
        "pipfile.lock",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "gradle.lockfile",
        "go.mod",
        "go.sum",
        "cargo.toml",
        "cargo.lock",
    }

    for file_change in files:
        name = PurePosixPath(file_change.path).name.lower()
        if name not in dependency_names:
            continue

        findings.append(
            Finding(
                rule_id="DEP001",
                title="Dependency manifest changed",
                severity="medium",
                message=(
                    "Dependency metadata changed. This tool does not "
                    "verify package vulnerabilities or version safety."
                ),
                file_path=file_change.path,
                recommendation=(
                    "Review new, removed, and upgraded dependencies; "
                    "check package provenance, lockfile changes, and "
                    "approved vulnerability scanning results."
                ),
                confidence="high",
            )
        )

    return findings


def detect_test_changes(files: list[FileChange]) -> list[Finding]:
    findings: list[Finding] = []

    for file_change in files:
        path = file_change.path.lower()
        name = PurePosixPath(path).name

        is_test_path = (
            "/tests/" in f"/{path}/"
            or "/test/" in f"/{path}/"
            or name.startswith("test_")
            or ".test." in name
            or ".spec." in name
        )

        if not is_test_path:
            continue

        if not file_change.deleted_lines:
            continue

        findings.append(
            Finding(
                rule_id="TEST001",
                title="Test lines removed",
                severity="medium",
                message=(
                    f"{len(file_change.deleted_lines)} test line(s) "
                    "were removed from this file."
                ),
                file_path=file_change.path,
                recommendation=(
                    "Confirm that removed tests are obsolete or replaced. "
                    "This signal alone does not prove coverage decreased."
                ),
                confidence="medium",
            )
        )

    return findings


def detect_change_size(
    files: list[FileChange],
    max_changed_files: int,
    max_added_lines: int,
) -> list[Finding]:
    findings: list[Finding] = []

    additions = sum(len(file.added_lines) for file in files)
    changed_files = len(files)

    if max_changed_files > 0 and changed_files > max_changed_files:
        findings.append(
            Finding(
                rule_id="SIZE001",
                title="Large number of changed files",
                severity="low",
                message=(
                    f"{changed_files} files changed; configured threshold "
                    f"is {max_changed_files}."
                ),
                recommendation=(
                    "Consider splitting unrelated changes into smaller "
                    "reviewable commits or pull requests."
                ),
                confidence="high",
            )
        )

    if max_added_lines > 0 and additions > max_added_lines:
        findings.append(
            Finding(
                rule_id="SIZE002",
                title="Large number of added lines",
                severity="low",
                message=(
                    f"{additions} lines added; configured threshold "
                    f"is {max_added_lines}."
                ),
                recommendation=(
                    "Review the change in logical sections and consider "
                    "splitting it if practical."
                ),
                confidence="high",
            )
        )

    return findings
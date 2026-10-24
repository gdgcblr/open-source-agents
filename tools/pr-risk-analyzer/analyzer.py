from models import AnalysisReport, FileChange, Finding
from rules import (
    detect_change_size,
    detect_dependency_changes,
    detect_infrastructure_changes,
    detect_secrets,
    detect_sensitive_paths,
    detect_test_changes,
)


DEFAULT_CONFIG = {
    "rules": {
        "secret_detection": True,
        "sensitive_paths": True,
        "infrastructure_changes": True,
        "dependency_changes": True,
        "test_changes": True,
        "change_size": True,
    },
    "thresholds": {
        "max_changed_files": 20,
        "max_added_lines": 1000,
    },
    "sensitive_paths": [
        "auth",
        "security",
        "permissions",
        "middleware",
        "crypto",
        "session",
    ],
}


def analyze_files(
    files: list[FileChange],
    config: dict | None = None,
) -> AnalysisReport:
    """Run enabled risk rules against parsed file changes."""
    config = config or DEFAULT_CONFIG
    enabled = config.get("rules", {})
    thresholds = config.get("thresholds", {})
    sensitive_paths = config.get("sensitive_paths", [])

    findings: list[Finding] = []

    if enabled.get("secret_detection", True):
        findings.extend(detect_secrets(files))

    if enabled.get("sensitive_paths", True):
        findings.extend(detect_sensitive_paths(files, sensitive_paths))

    if enabled.get("infrastructure_changes", True):
        findings.extend(detect_infrastructure_changes(files))

    if enabled.get("dependency_changes", True):
        findings.extend(detect_dependency_changes(files))

    if enabled.get("test_changes", True):
        findings.extend(detect_test_changes(files))

    if enabled.get("change_size", True):
        findings.extend(
            detect_change_size(
                files,
                max_changed_files=int(
                    thresholds.get("max_changed_files", 20)
                ),
                max_added_lines=int(
                    thresholds.get("max_added_lines", 1000)
                ),
            )
        )

    # Stable de-duplication: the same rule, path, line and title
    # should not generate duplicate findings.
    unique: dict[tuple, Finding] = {}
    for finding in findings:
        key = (
            finding.rule_id,
            finding.file_path,
            finding.line_number,
            finding.title,
        )
        unique[key] = finding

    ordered_findings = sorted(
        unique.values(),
        key=lambda item: (
            {
                "critical": 0,
                "high": 1,
                "medium": 2,
                "low": 3,
                "info": 4,
            }.get(item.severity, 5),
            item.file_path or "",
            item.line_number or 0,
            item.rule_id,
        ),
    )

    additions = sum(len(file.added_lines) for file in files)
    deletions = sum(len(file.deleted_lines) for file in files)

    return AnalysisReport(
        findings=ordered_findings,
        files_changed=len(files),
        additions=additions,
        deletions=deletions,
    )
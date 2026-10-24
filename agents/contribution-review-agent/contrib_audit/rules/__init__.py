"""Rules registry — imports every rule module and exposes run_all()."""
from __future__ import annotations

from pathlib import Path

from ..models import AuditResult, Finding
from . import structure, readme, secrets, scope, deps


def run_all(project_path: Path, repo_root: Path, git_available: bool = True) -> AuditResult:
    """Run every rule and return a consolidated AuditResult."""
    project_path = project_path.resolve()
    repo_root = repo_root.resolve()

    name = project_path.name
    result = AuditResult(project_path=project_path, project_name=name)

    # R01–R03: location and naming
    result.findings.extend(structure.check_location(project_path, repo_root))
    result.findings.extend(structure.check_naming(project_path))

    # R04: required files
    result.findings.extend(structure.check_required_files(project_path))

    # R05, R06, R10: README checks
    result.findings.extend(readme.check_headings(project_path, repo_root))
    result.findings.extend(readme.check_env_sync(project_path))
    result.findings.extend(readme.check_example_section(project_path))

    # R07: secrets scan
    result.findings.extend(secrets.scan_secrets(project_path))

    # R08: hygiene
    result.findings.extend(secrets.check_hygiene(project_path))

    # R09: scope (needs git)
    result.findings.extend(scope.check_scope(project_path, repo_root, git_available))

    # R11: deps declared
    result.findings.extend(deps.check_imports_declared(project_path))

    return result

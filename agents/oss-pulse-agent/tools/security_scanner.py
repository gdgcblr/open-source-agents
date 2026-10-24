"""Security configuration and risk analyzer.

Inspects observable security practices — SECURITY.md, Dependabot config,
code scanning workflows, dependency manifests, and branch protection.
This is NOT a vulnerability scan or security audit.
"""

from __future__ import annotations

import re
from typing import Optional

from models.report import (
    SecurityConfig,
    Evidence,
    DataCoverage,
    Finding,
    Category,
    Severity,
    Confidence,
)
from tools.github_client import GitHubClient

_MANIFEST_FILES = [
    "requirements.txt",
    "Pipfile",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "build.gradle",
    "build.gradle.kts",
    "pom.xml",
    "composer.json",
]


def check_security_configuration(
    owner: str,
    repo: str,
    client: GitHubClient,
) -> SecurityConfig:
    """Inspect public security readiness and automation settings."""
    evidence: list[Evidence] = []
    coverage: list[DataCoverage] = []
    findings: list[Finding] = []

    # 1. Security Policy check
    has_security_policy = False
    security_policy_url: Optional[str] = None
    try:
        policy_res = client.get(f"/repos/{owner}/{repo}/community/profile")
        if isinstance(policy_res, dict):
            sec_file = policy_res.get("files", {}).get("security_policy")
            if sec_file and sec_file.get("url"):
                has_security_policy = True
                security_policy_url = sec_file.get("html_url")

        if not has_security_policy:
            if client.file_exists(owner, repo, "SECURITY.md"):
                has_security_policy = True
                security_policy_url = f"https://github.com/{owner}/{repo}/blob/HEAD/SECURITY.md"
            elif client.file_exists(owner, repo, ".github/SECURITY.md"):
                has_security_policy = True
                security_policy_url = f"https://github.com/{owner}/{repo}/blob/HEAD/.github/SECURITY.md"

        evidence.append(
            Evidence(
                source="GitHub Community Profile / File Check",
                metric="has_security_policy",
                value=has_security_policy,
                context="SECURITY.md presence provides responsible vulnerability disclosure instructions"
                if has_security_policy
                else "No SECURITY.md file found in repository root or .github/",
                url=security_policy_url or f"https://github.com/{owner}/{repo}",
            )
        )
        coverage.append(
            DataCoverage(
                metric="security_policy",
                available=True,
                measurement_window="Repository files",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="security_policy",
                available=False,
                reason=f"Failed to check security policy: {str(e)}",
            )
        )

    # 2. Dependabot Configuration check
    has_dependabot_config = False
    dependabot_ecosystems: list[str] = []
    try:
        dependabot_yml = client.get_file_content(owner, repo, ".github/dependabot.yml")
        if not dependabot_yml:
            dependabot_yml = client.get_file_content(owner, repo, ".github/dependabot.yaml")

        if dependabot_yml:
            has_dependabot_config = True
            matches = re.findall(r'package-ecosystem:\s*["\']?([\w\-]+)["\']?', dependabot_yml)
            dependabot_ecosystems = sorted(list(set(matches)))

        evidence.append(
            Evidence(
                source="GitHub Repository Content (.github/dependabot.yml)",
                metric="has_dependabot_config",
                value=has_dependabot_config,
                context=f"Dependabot configured for ecosystems: {', '.join(dependabot_ecosystems)}"
                if has_dependabot_config
                else "No dependabot.yml configuration found",
                url=f"https://github.com/{owner}/{repo}/blob/HEAD/.github/dependabot.yml",
            )
        )
        coverage.append(
            DataCoverage(
                metric="dependabot_config",
                available=True,
                measurement_window=".github/ directory",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="dependabot_config",
                available=False,
                reason=f"Failed to check dependabot config: {str(e)}",
            )
        )

    # 3. Code Scanning Workflows check
    has_code_scanning = False
    code_scanning_tools: list[str] = []
    try:
        workflow_files = client.dir_listing(owner, repo, ".github/workflows")
        scanner_patterns = {
            "codeql": "CodeQL",
            "semgrep": "Semgrep",
            "snyk": "Snyk",
            "trivy": "Trivy",
            "sonar": "SonarQube/Cloud",
            "bandit": "Bandit",
            "scorecard": "OSSF Scorecard",
        }
        for item in workflow_files:
            name = item.get("name", "")
            if name.endswith((".yml", ".yaml")):
                content = client.get_file_content(owner, repo, f".github/workflows/{name}")
                if content:
                    content_lower = content.lower()
                    for pattern, tool_name in scanner_patterns.items():
                        if pattern in content_lower and tool_name not in code_scanning_tools:
                            code_scanning_tools.append(tool_name)

        has_code_scanning = len(code_scanning_tools) > 0
        evidence.append(
            Evidence(
                source="GitHub Actions Workflows (.github/workflows)",
                metric="has_code_scanning",
                value=has_code_scanning,
                context=f"Automated SAST/Code scanners detected: {', '.join(code_scanning_tools)}"
                if has_code_scanning
                else "No automated static analysis or security scan workflows detected",
                url=f"https://github.com/{owner}/{repo}/tree/HEAD/.github/workflows",
            )
        )
        coverage.append(
            DataCoverage(
                metric="code_scanning",
                available=True,
                sample_size=len(workflow_files),
                measurement_window="Workflow YAML definitions",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="code_scanning",
                available=False,
                reason=f"Failed to inspect workflow directory: {str(e)}",
            )
        )

    # 4. Dependency Manifests
    dependency_manifests: list[str] = []
    try:
        for fname in _MANIFEST_FILES:
            if client.file_exists(owner, repo, fname):
                dependency_manifests.append(fname)

        evidence.append(
            Evidence(
                source="Repository Root Manifest Check",
                metric="dependency_manifests",
                value=len(dependency_manifests),
                context=f"Detected package/dependency manifests: {', '.join(dependency_manifests)}"
                if dependency_manifests
                else "No standard package dependency manifest found in root",
                url=f"https://github.com/{owner}/{repo}",
            )
        )
        coverage.append(
            DataCoverage(
                metric="dependency_manifests",
                available=True,
                sample_size=len(_MANIFEST_FILES),
                measurement_window="Root directory",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="dependency_manifests",
                available=False,
                reason=f"Failed to inspect dependency manifests: {str(e)}",
            )
        )

    # 5. Branch Protection
    has_branch_protection: Optional[bool] = None
    try:
        repo_data = client.get(f"/repos/{owner}/{repo}")
        def_branch = repo_data.get("default_branch", "main") if isinstance(repo_data, dict) else "main"
        prot_res = client.get(f"/repos/{owner}/{repo}/branches/{def_branch}/protection")
        if prot_res is not None:
            has_branch_protection = True
        else:
            has_branch_protection = False

        evidence.append(
            Evidence(
                source=f"GitHub Branch Protection API ({def_branch})",
                metric="has_branch_protection",
                value=has_branch_protection,
                context=f"Default branch '{def_branch}' protection configured"
                if has_branch_protection
                else f"Branch protection not active or not publicly queryable on '{def_branch}'",
                url=f"https://github.com/{owner}/{repo}/settings/branches",
            )
        )
        coverage.append(
            DataCoverage(
                metric="branch_protection",
                available=True,
                measurement_window=f"Branch {def_branch}",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="branch_protection",
                available=False,
                reason=f"Branch protection check restricted or failed: {str(e)}",
            )
        )

    # Formulate Findings
    if not has_security_policy:
        findings.append(
            Finding(
                id="SEC-001",
                category=Category.SECURITY,
                severity=Severity.HIGH,
                title="Missing Security Policy (SECURITY.md)",
                description="The repository does not provide a public security disclosure guideline or private reporting channel.",
                evidence=[e for e in evidence if e.metric == "has_security_policy"],
                impact="Security researchers discovering vulnerabilities may publish them publicly or fail to notify maintainers.",
                recommended_fix="Create a SECURITY.md file detailing supported versions and private vulnerability reporting instructions.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    if not has_dependabot_config and len(dependency_manifests) > 0:
        findings.append(
            Finding(
                id="SEC-002",
                category=Category.SECURITY,
                severity=Severity.MEDIUM,
                title="No Automated Dependency Update Mechanism",
                description=f"Manifests were identified ({', '.join(dependency_manifests)}), but no Dependabot configuration (.github/dependabot.yml) exists.",
                evidence=[e for e in evidence if e.metric == "has_dependabot_config"],
                impact="Third-party package vulnerabilities may remain unpatched, leading to security debt.",
                recommended_fix="Add .github/dependabot.yml with scheduled updates for the discovered ecosystems.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    if not has_code_scanning:
        findings.append(
            Finding(
                id="SEC-003",
                category=Category.SECURITY,
                severity=Severity.MEDIUM,
                title="No Automated Code Scanning / SAST Pipeline",
                description="No static analysis workflows (such as GitHub CodeQL, Semgrep, or Trivy) were detected in .github/workflows.",
                evidence=[e for e in evidence if e.metric == "has_code_scanning"],
                impact="Bugs, insecure code patterns, and leaked secrets might reach production branches unflagged.",
                recommended_fix="Enable GitHub CodeQL analysis by adding a standard .github/workflows/codeql.yml workflow.",
                effort="medium",
                confidence=Confidence.HIGH,
            )
        )

    if has_branch_protection is False:
        findings.append(
            Finding(
                id="SEC-004",
                category=Category.SECURITY,
                severity=Severity.MEDIUM,
                title="No Default Branch Protection Rules Enabled",
                description="The default branch is open to direct pushes and lacks PR review enforcement.",
                evidence=[e for e in evidence if e.metric == "has_branch_protection"],
                impact="Increases risk of unintended breaks, bypassed tests, or unreviewed code reaching main.",
                recommended_fix="Enable branch protection requiring at least 1 pull request review and passing status checks.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    return SecurityConfig(
        has_security_policy=has_security_policy,
        security_policy_url=security_policy_url,
        has_dependabot_config=has_dependabot_config,
        dependabot_ecosystems=dependabot_ecosystems,
        has_code_scanning=has_code_scanning,
        code_scanning_tools=code_scanning_tools,
        has_secret_scanning=False,
        dependency_manifests=dependency_manifests,
        has_branch_protection=has_branch_protection,
        evidence=evidence,
        findings=findings,
        data_coverage=coverage,
    )

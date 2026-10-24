"""Documentation quality analyzer.

Evaluates not just whether documentation files exist, but whether
they contain the sections, examples, and clarity developers actually need.
"""

from __future__ import annotations

import re
from typing import Optional

from models.report import (
    DocumentationQuality,
    Evidence,
    DataCoverage,
    Finding,
    Category,
    Severity,
    Confidence,
)
from tools.github_client import GitHubClient


def inspect_documentation(
    owner: str,
    repo: str,
    client: GitHubClient,
) -> DocumentationQuality:
    """Inspect and evaluate repository documentation quality and completeness."""
    evidence: list[Evidence] = []
    coverage: list[DataCoverage] = []
    findings: list[Finding] = []

    # 1. README analysis
    has_readme = False
    readme_length_chars = 0
    readme_sections: list[str] = []
    readme_has_badges = False
    readme_has_installation = False
    readme_has_usage = False
    readme_has_examples = False
    readme_has_api_docs = False

    try:
        readme_content = client.get_file_content(owner, repo, "README.md")
        if not readme_content:
            readme_content = client.get_file_content(owner, repo, "readme.md")

        if readme_content:
            has_readme = True
            readme_length_chars = len(readme_content)

            header_matches = re.findall(r"^#{1,3}\s+(.+)$", readme_content, re.MULTILINE)
            readme_sections = [h.strip() for h in header_matches]

            readme_has_badges = bool(
                re.search(r"\[!\[.*?\]\(.*?\)\]|!\[.*?badge.*?\]|shields\.io", readme_content, re.IGNORECASE)
            )

            lower_secs = [s.lower() for s in readme_sections]
            installation_keywords = ["install", "installation", "getting started", "setup", "quickstart", "quick start"]
            usage_keywords = ["usage", "how to use", "guide", "tutorial", "running"]
            api_keywords = ["api", "reference", "documentation", "endpoints", "sdk"]

            readme_has_installation = any(any(k in sec for k in installation_keywords) for sec in lower_secs)
            readme_has_usage = any(any(k in sec for k in usage_keywords) for sec in lower_secs)
            readme_has_examples = "```" in readme_content or readme_has_usage
            readme_has_api_docs = any(any(k in sec for k in api_keywords) for sec in lower_secs)

            evidence.append(
                Evidence(
                    source="README.md Content Analysis",
                    metric="readme_quality",
                    value=readme_length_chars,
                    context=f"README length is {readme_length_chars} characters with {len(readme_sections)} sections. "
                    f"Installation: {readme_has_installation}, Usage: {readme_has_usage}, Examples: {readme_has_examples}",
                    url=f"https://github.com/{owner}/{repo}#readme",
                )
            )
        else:
            evidence.append(
                Evidence(
                    source="README.md File Check",
                    metric="has_readme",
                    value=False,
                    context="No README.md file found in repository root",
                    url=f"https://github.com/{owner}/{repo}",
                )
            )

        coverage.append(
            DataCoverage(
                metric="readme",
                available=True,
                measurement_window="README.md text parsing",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="readme",
                available=False,
                reason=f"Failed to inspect README: {str(e)}",
            )
        )

    # 2. CONTRIBUTING guide check
    has_contributing = False
    try:
        has_contributing = (
            client.file_exists(owner, repo, "CONTRIBUTING.md")
            or client.file_exists(owner, repo, ".github/CONTRIBUTING.md")
            or client.file_exists(owner, repo, "docs/CONTRIBUTING.md")
        )
        evidence.append(
            Evidence(
                source="File Check (CONTRIBUTING.md)",
                metric="has_contributing",
                value=has_contributing,
                context="CONTRIBUTING.md guides onboarding, setup, and PR conventions"
                if has_contributing
                else "No CONTRIBUTING.md guide located",
                url=f"https://github.com/{owner}/{repo}/blob/HEAD/CONTRIBUTING.md"
                if has_contributing
                else f"https://github.com/{owner}/{repo}",
            )
        )
        coverage.append(
            DataCoverage(metric="contributing_guide", available=True, measurement_window="Repository files")
        )
    except Exception as e:
        coverage.append(
            DataCoverage(metric="contributing_guide", available=False, reason=f"Failed to check contributing guide: {str(e)}")
        )

    # 3. LICENSE check
    has_license = False
    license_type: Optional[str] = None
    try:
        repo_data = client.get(f"/repos/{owner}/{repo}")
        if isinstance(repo_data, dict) and repo_data.get("license"):
            has_license = True
            lic = repo_data.get("license", {})
            license_type = lic.get("spdx_id") or lic.get("name")
        else:
            has_license = (
                client.file_exists(owner, repo, "LICENSE")
                or client.file_exists(owner, repo, "LICENSE.md")
                or client.file_exists(owner, repo, "LICENSE.txt")
            )

        evidence.append(
            Evidence(
                source="GitHub License API / File Check",
                metric="has_license",
                value=license_type or has_license,
                context=f"Open-source license detected: {license_type or 'LICENSE file present'}"
                if has_license
                else "No recognized license file or SPDX identifier found",
                url=f"https://github.com/{owner}/{repo}/blob/HEAD/LICENSE"
                if has_license
                else f"https://github.com/{owner}/{repo}",
            )
        )
        coverage.append(
            DataCoverage(metric="license", available=True, measurement_window="License metadata & files")
        )
    except Exception as e:
        coverage.append(
            DataCoverage(metric="license", available=False, reason=f"Failed to check license: {str(e)}")
        )

    # 4. Code of Conduct, Changelog, Templates & Docs Directory
    has_code_of_conduct = False
    has_changelog = False
    has_issue_templates = False
    has_pr_templates = False
    has_docs_directory = False

    try:
        has_code_of_conduct = (
            client.file_exists(owner, repo, "CODE_OF_CONDUCT.md")
            or client.file_exists(owner, repo, ".github/CODE_OF_CONDUCT.md")
        )
        has_changelog = (
            client.file_exists(owner, repo, "CHANGELOG.md")
            or client.file_exists(owner, repo, "CHANGELOG")
            or client.file_exists(owner, repo, "HISTORY.md")
        )
        has_issue_templates = (
            client.file_exists(owner, repo, ".github/ISSUE_TEMPLATE")
            or client.file_exists(owner, repo, ".github/issue_template.md")
        )
        has_pr_templates = (
            client.file_exists(owner, repo, ".github/PULL_REQUEST_TEMPLATE.md")
            or client.file_exists(owner, repo, ".github/PULL_REQUEST_TEMPLATE")
        )
        has_docs_directory = client.file_exists(owner, repo, "docs")

        coverage.append(
            DataCoverage(metric="governance_templates", available=True, measurement_window="Repository governance files")
        )
    except Exception as e:
        coverage.append(
            DataCoverage(metric="governance_templates", available=False, reason=f"Failed to check templates: {str(e)}")
        )

    # Formulate Findings
    if not has_readme:
        findings.append(
            Finding(
                id="DOC-001",
                category=Category.DOCUMENTATION,
                severity=Severity.CRITICAL,
                title="Missing README.md File",
                description="The project has no README in the root directory, giving newcomers zero context on the project.",
                evidence=[e for e in evidence if e.metric == "has_readme"],
                impact="Severely impairs adoption, comprehension, and contribution.",
                recommended_fix="Create a comprehensive README.md with project description, installation, and usage examples.",
                effort="medium",
                confidence=Confidence.HIGH,
            )
        )
    elif readme_length_chars < 500:
        findings.append(
            Finding(
                id="DOC-002",
                category=Category.DOCUMENTATION,
                severity=Severity.HIGH,
                title="Underdeveloped README (<500 Characters)",
                description=f"README is very brief ({readme_length_chars} characters), missing essential setup and architecture details.",
                evidence=[e for e in evidence if e.metric == "readme_quality"],
                impact="Users and potential contributors must read source code to understand how to get started.",
                recommended_fix="Expand the README with installation steps, code snippets, and prerequisites.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    if has_readme and not readme_has_installation:
        findings.append(
            Finding(
                id="DOC-003",
                category=Category.DOCUMENTATION,
                severity=Severity.MEDIUM,
                title="No Dedicated Installation / Setup Section in README",
                description="The README lacks an explicit 'Installation' or 'Getting Started' section header.",
                evidence=[e for e in evidence if e.metric == "readme_quality"],
                impact="New developers may struggle to set up local dependencies and environment.",
                recommended_fix="Add an 'Installation' header with copy-paste commands (e.g. pip, npm, cargo).",
                effort="low",
                confidence=Confidence.MEDIUM,
            )
        )

    if not has_license:
        findings.append(
            Finding(
                id="DOC-004",
                category=Category.DOCUMENTATION,
                severity=Severity.HIGH,
                title="Missing Open Source License (LICENSE)",
                description="Without an explicit license, default copyright laws apply, meaning nobody can legally use, modify, or fork the code.",
                evidence=[e for e in evidence if e.metric == "has_license"],
                impact="Blocks institutional and community adoption due to legal ambiguity.",
                recommended_fix="Choose and commit an OSI-approved license (e.g., Apache-2.0 or MIT).",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    if not has_contributing:
        findings.append(
            Finding(
                id="DOC-005",
                category=Category.DOCUMENTATION,
                severity=Severity.MEDIUM,
                title="Missing Contribution Guidelines (CONTRIBUTING.md)",
                description="No guidelines specifying testing procedures, pull request standards, or branch naming conventions.",
                evidence=[e for e in evidence if e.metric == "has_contributing"],
                impact="Increases maintainer burden reviewing non-conforming pull requests.",
                recommended_fix="Create CONTRIBUTING.md outlining PR workflows, local testing, and coding standards.",
                effort="medium",
                confidence=Confidence.HIGH,
            )
        )

    if not has_issue_templates:
        findings.append(
            Finding(
                id="DOC-006",
                category=Category.DOCUMENTATION,
                severity=Severity.LOW,
                title="No Issue or Pull Request Templates",
                description="Structured issue forms (.github/ISSUE_TEMPLATE) are missing.",
                evidence=[],
                impact="Bug reports may lack reproduction steps, OS versions, or system details.",
                recommended_fix="Add GitHub Issue Form templates for Bug Reports and Feature Requests.",
                effort="low",
                confidence=Confidence.MEDIUM,
            )
        )

    return DocumentationQuality(
        has_readme=has_readme,
        readme_length_chars=readme_length_chars,
        readme_has_badges=readme_has_badges,
        readme_has_installation=readme_has_installation,
        readme_has_usage=readme_has_usage,
        readme_has_examples=readme_has_examples,
        readme_has_api_docs=readme_has_api_docs,
        readme_sections=readme_sections,
        has_contributing=has_contributing,
        has_license=has_license,
        license_type=license_type,
        has_code_of_conduct=has_code_of_conduct,
        has_changelog=has_changelog,
        has_issue_templates=has_issue_templates,
        has_pr_templates=has_pr_templates,
        has_docs_directory=has_docs_directory,
        evidence=evidence,
        findings=findings,
        data_coverage=coverage,
    )

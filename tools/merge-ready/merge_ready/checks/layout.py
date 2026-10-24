"""Checks for project layout, naming conventions, and required files (L01, L02, F01)."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import MAX_FILE_COUNT, MAX_FILE_SIZE, ProjectContext

KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
GENERIC_NAMES = {
    "my-agent",
    "final-project",
    "test",
    "demo",
    "my-tool",
    "final-test",
    "helper",
    "agent",
    "tool",
    "project",
    "new-agent",
    "new-tool",
}
ACCEPTED_MANIFESTS = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
}


def check_l01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """L01: Project sits under agents/<slug>/ or tools/<slug>/."""
    rule_id = "L01"
    name = "Dedicated Directory Location"
    source = config.get("source_rule", "CONTRIBUTING.md Step 4 & Directory Standards")

    if ctx.category not in ("agents", "tools"):
        msg = f"Project directory is located under '{ctx.category}', but must be inside 'agents/' or 'tools/'."
        fix = f"Move your project to agents/{ctx.slug}/ or tools/{ctx.slug}/."
        finding = Finding(
            rule_id=rule_id,
            severity=Severity.ERROR,
            message=msg,
            path=str(ctx.project_path.name),
            fix=fix,
            source_rule=source,
        )
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.FAIL, findings=[finding])

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)


def check_l02(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """L02: Naming rules: lowercase kebab-case, generic-name deny-list, and uniqueness."""
    rule_id = "L02"
    name = "Naming Conventions"
    source = config.get("source_rule", "CONTRIBUTING.md Directory & Naming Rules")
    slug = ctx.slug
    findings: list[Finding] = []

    if not KEBAB_CASE_PATTERN.match(slug):
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Directory name '{slug}' does not follow lowercase kebab-case naming.",
                path=slug,
                evidence=f"Directory name is '{slug}'. Must match ^[a-z0-9]+(-[a-z0-9]+)*$",
                fix=f"Rename directory to lowercase kebab-case (e.g. '{slug.lower().replace('_', '-')}')",
                source_rule=source,
            )
        )

    if slug.lower() in GENERIC_NAMES:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Directory name '{slug}' is generic and does not describe project function.",
                path=slug,
                evidence=f"Name '{slug}' is present in the generic name blocklist.",
                fix="Choose a specific, descriptive name (e.g. 'research-paper-synthesizer', 'mcp-doc-search').",
                source_rule=source,
            )
        )

    # Uniqueness check against base branch or existing sibling folders
    if ctx.repo_root and ctx.base_ref and ctx.category in ("agents", "tools"):
        try:
            tree_output = subprocess.run(
                ["git", "ls-tree", "--name-only", ctx.base_ref, f"{ctx.category}/"],
                cwd=str(ctx.repo_root),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
            existing_names = {line.strip().split("/")[-1] for line in tree_output if line.strip() != "README.md"}
            if slug in existing_names:
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=Severity.ERROR,
                        message=f"Project name '{slug}' conflicts with an existing project in {ctx.category}/ on base '{ctx.base_ref}'.",
                        path=slug,
                        evidence=f"Base ref '{ctx.base_ref}' already contains {ctx.category}/{slug}/",
                        fix=f"Choose a unique descriptive name for your contribution in {ctx.category}/.",
                        source_rule=source,
                    )
                )
        except Exception:
            pass

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.FAIL, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)


def check_f01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """F01: Required file standards (README.md, .env.example, .gitignore, manifest)."""
    rule_id = "F01"
    name = "Required File Standards"
    source = config.get("source_rule", "CONTRIBUTING.md Step 5 & Step 7")
    findings: list[Finding] = []

    posix_files = {p.as_posix() for p in ctx.files}

    if "README.md" not in posix_files:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message="Missing required file 'README.md'.",
                path="README.md",
                evidence="File 'README.md' not found in project directory.",
                fix="Copy template/README.md to your project folder and document your project.",
                source_rule=source,
            )
        )

    if ".env.example" not in posix_files:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message="Missing required file '.env.example'.",
                path=".env.example",
                evidence="File '.env.example' not found in project directory.",
                fix="Copy template/.env.example to your project folder and configure placeholders.",
                source_rule=source,
            )
        )

    if ".gitignore" not in posix_files:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message="Missing required file '.gitignore'.",
                path=".gitignore",
                evidence="File '.gitignore' not found in project directory.",
                fix="Copy template/.gitignore to your project folder to prevent tracking secrets and environments.",
                source_rule=source,
            )
        )

    has_manifest = any(m in posix_files for m in ACCEPTED_MANIFESTS)
    if not has_manifest:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message="No recognized dependency manifest file found.",
                path=ctx.slug,
                evidence=f"None of the accepted manifests ({', '.join(sorted(ACCEPTED_MANIFESTS))}) found.",
                fix="Add a dependency manifest (e.g., requirements.txt, pyproject.toml, package.json).",
                source_rule=source,
            )
        )

    # Defensive resource & security limits
    if ctx.limit_exceeded_file_count:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Project exceeds maximum allowed file count ({MAX_FILE_COUNT} files). Scanning truncated to prevent resource exhaustion.",
                path=ctx.slug,
                evidence=f"Directory traversal halted at {MAX_FILE_COUNT} files limit.",
                fix="Remove extraneous files, build artifacts, test caches, or bloated directories from your contribution.",
                source_rule=source,
            )
        )

    for oversized_path, file_size in ctx.oversized_files:
        limit_mb = MAX_FILE_SIZE // (1024 * 1024)
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"File '{oversized_path}' ({file_size} bytes) exceeds the maximum allowed file size of {limit_mb} MB.",
                path=oversized_path,
                evidence=f"File size {file_size} bytes exceeds {MAX_FILE_SIZE} bytes limit.",
                fix="Remove oversized data, binaries, or model weights. Store large assets externally.",
                source_rule=source,
            )
        )

    for symlink_path, target_path in ctx.rejected_symlinks:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Symlink '{symlink_path}' resolves to external path '{target_path}' outside project boundary.",
                path=symlink_path,
                evidence=f"Potential directory traversal rejected: '{symlink_path}' -> '{target_path}'",
                fix="Remove symlinks pointing outside the dedicated project directory.",
                source_rule=source,
            )
        )

    for unreadable_path, err_msg in ctx.unreadable_files:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"File '{unreadable_path}' could not be inspected: {err_msg}",
                path=unreadable_path,
                evidence=err_msg,
                fix="Ensure file permissions allow reading and file is not locked.",
                source_rule=source,
            )
        )

    if getattr(ctx, "config_errors", None):
        for err_msg in ctx.config_errors:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=f"Configuration file error: {err_msg}",
                    path="rules.toml",
                    evidence=err_msg,
                    fix="Fix syntax or schema errors in rules.toml.",
                    source_rule="rules.toml",
                )
            )

    if findings:
        verdict = Verdict.ERROR if getattr(ctx, "config_errors", None) else Verdict.FAIL
        return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)

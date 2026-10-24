"""Checks for template residue, required documentation sections, and command consistency (D01, D02, R02)."""

from __future__ import annotations

import re
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import ProjectContext

REQUIRED_SECTIONS = [
    "Overview",
    "Technical Stack",
    "Architecture & Data Flow",
    "Prerequisites",
    "Installation & Setup",
    "Configuration & Environment Variables",
    "How to Run",
    "Example Input & Output",
    "How to Test",
    "Known Limitations",
    "Security & Privacy Considerations",
    "Future Improvements",
    "License",
]

DEFAULT_PLACEHOLDERS = [
    "[Project Name]",
    "[One-sentence summary of what this project does and the value it provides.]",
    "[Language Runtime, e.g., Python 3.10+ or Node.js 18+]",
    "[Package manager, e.g., pip / uv / npm / pnpm]",
    "[Required API keys or service accounts]",
    "Feature 1: Brief description of the capability.",
    "Feature 2: Brief description of the capability.",
    "Feature 3: Brief description of the capability.",
    "\"Analyze the repository structure of gdgcblr/open-source-agents and list the core directories.\"",
]


def check_d01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """D01: Detect unmodified template placeholders and unchanged sample outputs."""
    rule_id = "D01"
    name = "Template Residue Detection"
    source = config.get("source_rule", "template/README.md & CONTRIBUTING.md Step 7")

    content = ctx.read_text("README.md")
    if content is None:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="README.md is missing or unreadable.",
        )

    # Extract dynamic placeholders from loaded template
    placeholders = list(DEFAULT_PLACEHOLDERS)
    template_lines = ctx.template_readme.splitlines()
    for line in template_lines:
        line_strip = line.strip()
        if line_strip.startswith("- Feature ") and "Brief description" in line_strip:
            if line_strip not in placeholders:
                placeholders.append(line_strip)
        elif line_strip.startswith("> [One-sentence"):
            placeholders.append(line_strip.lstrip("> "))

    findings: list[Finding] = []
    lines = content.splitlines()
    for line_idx, line in enumerate(lines, 1):
        # Exclude lines that are clearly documentation discussing placeholders
        trimmed = line.strip()
        if "placeholder" in trimmed.lower() or "template" in trimmed.lower() and "residue" in trimmed.lower():
            continue
        for ph in placeholders:
            if ph in line:
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=Severity.ERROR,
                        message=f"Unmodified template placeholder '{ph}' detected in README.md.",
                        path="README.md",
                        line=line_idx,
                        evidence=trimmed[:120],
                        fix=f"Replace template placeholder with your project's actual documentation.",
                        source_rule=source,
                    )
                )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.FAIL, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)


def check_d02(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """D02: Check presence and non-emptiness of all required template sections."""
    rule_id = "D02"
    name = "Required Documentation Sections"
    source = config.get("source_rule", "template/README.md")

    content = ctx.read_text("README.md")
    if content is None:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="README.md is missing or unreadable.",
        )

    # Normalize headings: match level 2 headings to preserve subsections within their parent section
    header_pattern = re.compile(r"^##\s+([^#\n\r]+)$", re.MULTILINE)
    matches = list(header_pattern.finditer(content))
    findings: list[Finding] = []
    section_blocks: dict[str, str] = {}
    for i, match in enumerate(matches):
        sec_name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_blocks[sec_name.lower()] = content[start:end].strip()

    for sec in REQUIRED_SECTIONS:
        found_key = None
        for k in section_blocks:
            if sec.lower() in k:
                found_key = k
                break

        if not found_key:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.WARNING,
                    message=f"Missing required documentation section: '{sec}'.",
                    path="README.md",
                    fix=f"Add a '## {sec}' section to README.md. If inapplicable, explain why (e.g. 'N/A - standalone utility').",
                    source_rule=source,
                )
            )
        else:
            body = section_blocks[found_key]
            if not body:
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=Severity.WARNING,
                        message=f"Section '{sec}' exists but appears to have empty content.",
                        path="README.md",
                        fix=f"Document the '{sec}' section, or state N/A with a short explanation.",
                        source_rule=source,
                    )
                )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.WARN, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)


def check_r02(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """R02: Check that commands in README reference files and scripts that exist."""
    rule_id = "R02"
    name = "README Command References Consistency"
    source = config.get("source_rule", "PULL_REQUEST_TEMPLATE.md Reproducible Setup")

    content = ctx.read_text("README.md")
    if content is None:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="README.md is missing or unreadable.",
        )

    findings: list[Finding] = []
    posix_files = {p.as_posix() for p in ctx.files}

    # Extract fenced code blocks
    code_blocks = re.findall(r"```(?:bash|sh|powershell|cmd|text)?\n(.*?)```", content, re.DOTALL)
    for block in code_blocks:
        for line in block.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue

            # Check pip install -r <file>
            pip_match = re.search(r"pip\s+install\s+-r\s+([^\s]+)", line_str)
            if pip_match:
                req_file = pip_match.group(1).strip()
                if req_file not in posix_files:
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.WARNING,
                            message=f"Command references requirements file '{req_file}' which does not exist.",
                            path="README.md",
                            evidence=line_str,
                            fix=f"Create '{req_file}' or update the installation command in README.md.",
                            source_rule=source,
                        )
                    )

            # Check python <script.py>
            py_match = re.search(r"(?:python|python3|py)\s+([a-zA-Z0-9_\-\./\\]+\.py)", line_str)
            if py_match:
                script_file = py_match.group(1).replace("\\", "/").strip("./")
                if script_file not in posix_files:
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.WARNING,
                            message=f"Command references script '{script_file}' which does not exist in the project.",
                            path="README.md",
                            evidence=line_str,
                            fix=f"Verify script '{script_file}' exists or update the run command in README.md.",
                            source_rule=source,
                        )
                    )

            # Check cp .env.example .env
            if "cp .env.example" in line_str or "Copy-Item template/.env.example" in line_str or "Copy-Item .env.example" in line_str:
                if ".env.example" not in posix_files:
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.WARNING,
                            message="Command references '.env.example' which is missing from the project.",
                            path="README.md",
                            evidence=line_str,
                            fix="Add a '.env.example' file to the project folder.",
                            source_rule=source,
                        )
                    )

            # Check cd agents/<slug> or cd tools/<slug>
            cd_match = re.search(r"cd\s+(agents|tools)/([a-zA-Z0-9_\-]+)", line_str)
            if cd_match:
                cd_cat, cd_slug = cd_match.groups()
                if cd_slug != ctx.slug and cd_slug != "<project-slug>":
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.WARNING,
                            message=f"Directory navigation command specifies '{cd_cat}/{cd_slug}', but this project is '{ctx.category}/{ctx.slug}'.",
                            path="README.md",
                            evidence=line_str,
                            fix=f"Update the cd command to 'cd {ctx.category}/{ctx.slug}'.",
                            source_rule=source,
                        )
                    )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.WARN, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)

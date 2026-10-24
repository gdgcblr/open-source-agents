from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

SECRET_PATTERNS = [
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("Possible GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("Possible Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}\b")),
    ("Possible AWS access key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Possible credential assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|password)\b\s*[:=]\s*['\"]?(?!your_|change_me|example|placeholder|<)[A-Za-z0-9/+=_.-]{12,}"
    )),
]
TEXT_SUFFIXES = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".md", ".txt", ".sh"}
WEIGHTS = {
    "README exists": 12,
    "Installation instructions": 10,
    "Usage example": 8,
    "Dependency manifest": 10,
    "Ignore rules": 10,
    "Environment template": 8,
    "Tests present": 8,
    "License present": 8,
    "Contribution guidance": 6,
    "Configuration documented": 6,
    "Secret-pattern scan": 8,
    "Project structure": 6,
}


def _find(files: dict[str, str], names: set[str]) -> str | None:
    for path in files:
        if PurePosixPath(path).name.lower() in names:
            return path
    return None


def _add(findings, title, severity, status, details, recommendation, evidence=None, weight=0):
    findings.append({
        "title": title,
        "severity": severity,
        "status": status,
        "details": details,
        "recommendation": recommendation,
        "evidence": evidence,
        "weight": weight,
    })


def analyze_project(files: dict[str, str]) -> dict[str, Any]:
    """Analyze a mapping of safe relative file paths to decoded text contents."""
    findings = []
    paths = list(files.keys())
    lower_paths = [p.lower() for p in paths]
    basenames = {PurePosixPath(p).name.lower(): p for p in paths}
    readme_path = _find(files, {"readme.md", "readme.rst", "readme.txt"})
    readme = files.get(readme_path, "") if readme_path else ""
    readme_l = readme.lower()

    # README
    if readme_path:
        _add(findings, "README exists", "Info", "PASS",
             f"Found `{readme_path}`.", "Keep setup and usage instructions current.", weight=WEIGHTS["README exists"])
    else:
        _add(findings, "README exists", "High", "MISSING",
             "No README file was found at any directory level.", "Add a README with purpose, setup, usage, examples, and limitations.", weight=WEIGHTS["README exists"])

    # Documentation sections
    install_terms = ("install", "installation", "getting started", "setup", "pip install", "uv sync")
    if any(t in readme_l for t in install_terms):
        _add(findings, "Installation instructions", "Info", "PASS", "README appears to mention installation or setup.", "Verify the commands work in a clean environment.", weight=WEIGHTS["Installation instructions"])
    else:
        _add(findings, "Installation instructions", "Medium", "NEEDS ATTENTION", "Could not find a clear installation/setup section in the README.", "Document prerequisites, environment setup, and exact install/run commands.", weight=WEIGHTS["Installation instructions"])

    usage_terms = ("usage", "how to use", "quickstart", "quick start", "example", "run the app", "streamlit run")
    if any(t in readme_l for t in usage_terms):
        _add(findings, "Usage example", "Info", "PASS", "README appears to include usage guidance.", "Include a minimal end-to-end example and expected output.", weight=WEIGHTS["Usage example"])
    else:
        _add(findings, "Usage example", "Low", "NEEDS ATTENTION", "No obvious usage/example section was detected in the README.", "Add a short example showing input, command, and expected output.", weight=WEIGHTS["Usage example"])

    # Dependencies
    dep_path = _find(files, {"requirements.txt", "pyproject.toml", "pipfile", "poetry.lock", "environment.yml", "package.json"})
    if dep_path:
        _add(findings, "Dependency manifest", "Info", "PASS", f"Found `{dep_path}`.", "Ensure dependencies are minimal and reproducible; pin versions where appropriate.", weight=WEIGHTS["Dependency manifest"])
    else:
        _add(findings, "Dependency manifest", "Medium", "MISSING", "No common dependency manifest was found.", "Add requirements.txt, pyproject.toml, package.json, or the manifest appropriate to the project.", weight=WEIGHTS["Dependency manifest"])

    # Ignore rules and environment template
    ignore_path = _find(files, {".gitignore"})
    if ignore_path:
        ignore_text = files[ignore_path]
        has_env_rule = any(line.strip() in {".env", ".env*", "*.pem", "secrets.json"} for line in ignore_text.splitlines())
        _add(findings, "Ignore rules", "Info" if has_env_rule else "Medium", "PASS" if has_env_rule else "NEEDS ATTENTION",
             f"Found `{ignore_path}`." + ("" if has_env_rule else " It may not exclude common environment/secret files."),
             "Ignore `.env`, virtual environments, caches, build output, and local secrets. Review rules for your stack.",
             weight=WEIGHTS["Ignore rules"])
    else:
        _add(findings, "Ignore rules", "Medium", "MISSING", "No .gitignore file was found.", "Add a .gitignore suitable for the language and exclude local secrets and generated files.", weight=WEIGHTS["Ignore rules"])

    env_example = _find(files, {".env.example", ".env.sample", "example.env"})
    if env_example:
        _add(findings, "Environment template", "Info", "PASS", f"Found `{env_example}`.", "Use placeholder values only; never include live credentials.", weight=WEIGHTS["Environment template"])
    else:
        _add(findings, "Environment template", "Low", "MISSING", "No `.env.example` or equivalent template was found.", "If environment variables are required, document their names in a safe template without real values.", weight=WEIGHTS["Environment template"])

    # Tests
    test_paths = [p for p in paths if re.search(r"(^|/)(tests?|specs?)(/|$)|(^|/)(test_[^/]+\.py|[^/]+_test\.py)$", p, re.I)]
    if test_paths:
        _add(findings, "Tests present", "Info", "PASS", f"Found {len(test_paths)} test-related path(s).", "Document how to run tests and include representative success/failure cases.", weight=WEIGHTS["Tests present"])
    else:
        _add(findings, "Tests present", "Low", "MISSING", "No obvious tests/ or test_*.py files were found.", "Add a small test suite for core behavior and document the test command.", weight=WEIGHTS["Tests present"])

    # License / contributing
    license_path = _find(files, {"license", "license.md", "license.txt", "copying"})
    if license_path:
        _add(findings, "License present", "Info", "PASS", f"Found `{license_path}`.", "Confirm the chosen license matches your intentions and dependencies.", weight=WEIGHTS["License present"])
    else:
        _add(findings, "License present", "Low", "MISSING", "No common license file was found.", "Choose an appropriate license and add its complete text; do not assume code is automatically reusable.", weight=WEIGHTS["License present"])

    contrib_path = _find(files, {"contributing.md", "contributing.rst"})
    if contrib_path:
        _add(findings, "Contribution guidance", "Info", "PASS", f"Found `{contrib_path}`.", "Explain issues, branches, tests, and pull-request expectations.", weight=WEIGHTS["Contribution guidance"])
    else:
        _add(findings, "Contribution guidance", "Low", "MISSING", "No CONTRIBUTING guide was found.", "For a community-facing project, explain how to report issues and submit changes.", weight=WEIGHTS["Contribution guidance"])

    config_terms = ("environment variable", ".env", "configuration", "api key", "api_key")
    if any(t in readme_l for t in config_terms):
        _add(findings, "Configuration documented", "Info", "PASS", "README appears to mention configuration or environment variables.", "List required variables and safe example values.", weight=WEIGHTS["Configuration documented"])
    else:
        _add(findings, "Configuration documented", "Low", "NEEDS ATTENTION", "Could not detect configuration guidance in the README.", "Document required configuration and how to supply it without committing secrets.", weight=WEIGHTS["Configuration documented"])

    # Secret pattern scan; report only filename and pattern name, never matching secret text.
    secret_hits = []
    for path, content in files.items():
        if PurePosixPath(path).suffix.lower() not in TEXT_SUFFIXES and PurePosixPath(path).name.lower() not in {".env", "dockerfile"}:
            continue
        if PurePosixPath(path).name.lower() in {".env.example", ".env.sample", "example.env"}:
            continue
        for pattern_name, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(content):
                line_no = content[:match.start()].count("\n") + 1
                secret_hits.append((path, line_no, pattern_name))
                if len(secret_hits) >= 20:
                    break
            if len(secret_hits) >= 20:
                break
        if len(secret_hits) >= 20:
            break
    if secret_hits:
        evidence = "\n".join(f"{p}:{line}: {name}" for p, line, name in secret_hits[:10])
        _add(findings, "Secret-pattern scan", "High", "REVIEW REQUIRED",
             f"Found {len(secret_hits)} possible credential pattern(s). Matches can be false positives; secret values are intentionally not displayed.",
             "Inspect the listed lines locally. If a real secret was committed, revoke/rotate it and remove it from repository history as appropriate.",
             evidence=evidence, weight=WEIGHTS["Secret-pattern scan"])
    else:
        _add(findings, "Secret-pattern scan", "Info", "NO PATTERN DETECTED",
             "No supported common credential patterns were detected in eligible text files. This does not prove the project contains no secrets.",
             "Use a dedicated secret scanner and review files before publishing.", weight=WEIGHTS["Secret-pattern scan"])

    # Project structure
    root_level = [p for p in paths if "/" not in p.strip("/")]
    if len(paths) >= 2:
        _add(findings, "Project structure", "Info", "PASS", f"Found {len(paths)} readable text files, including {len(root_level)} at archive root.", "Keep entry points, tests, documentation, and configuration easy to locate.", weight=WEIGHTS["Project structure"])
    else:
        _add(findings, "Project structure", "Low", "NEEDS ATTENTION", "Very few readable text files were detected.", "Confirm the ZIP contains the intended project files and excludes only generated/binary files.", weight=WEIGHTS["Project structure"])

    total_weight = sum(f["weight"] for f in findings)
    earned = sum(f["weight"] for f in findings if f["status"] in {"PASS", "NO PATTERN DETECTED"})
    score = round(100 * earned / total_weight) if total_weight else 0
    high = sum(1 for f in findings if f["severity"] == "High" and f["status"] not in {"PASS", "NO PATTERN DETECTED"})
    attention = sum(1 for f in findings if f["status"] not in {"PASS", "NO PATTERN DETECTED"})
    return {
        "project": "OpenSource Guardian",
        "score": score,
        "passed": sum(1 for f in findings if f["status"] in {"PASS", "NO PATTERN DETECTED"}),
        "attention": attention,
        "high": high,
        "findings": findings,
        "inventory": sorted(paths),
        "disclaimer": "Heuristic readiness check only; not a complete code review or security audit.",
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# OpenSource Guardian Report", "",
        f"- **Readiness score:** {report['score']}/100",
        f"- **Checks passed:** {report['passed']}",
        f"- **Needs attention:** {report['attention']}",
        f"- **High-priority findings:** {report['high']}", "",
        "> This is a heuristic checklist, not a guarantee of quality or security.", "",
        "## Findings", "",
    ]
    for f in report["findings"]:
        lines += [
            f"### [{f['severity']}] {f['title']} — {f['status']}",
            f["details"],
            f"**Suggested action:** {f['recommendation']}",
        ]
        if f.get("evidence"):
            lines += ["", "```text", f["evidence"], "```"]
        lines.append("")
    lines += ["## File inventory", ""] + [f"- `{p}`" for p in report["inventory"]]
    return "\n".join(lines) + "\n"

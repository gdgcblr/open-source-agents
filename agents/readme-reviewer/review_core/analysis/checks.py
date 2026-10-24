"""Deterministic pass/fail checks, grouped by the four review criteria.

Every check is plain Python (no LLM) and returns:
    {"id", "criterion", "passed", "applicable", "reason"}
`applicable=False` means the check does not apply to this project (for example a
Python-only rule on a Node project); it is ignored when scoring.
"""

import os
import re

from . import tools
from .links import check_links

CRITERIA = ["reproducibility", "documentation", "security", "scope"]


def _check(check_id, criterion, passed, reason, applicable=True):
    return {
        "id": check_id,
        "criterion": criterion,
        "passed": bool(passed),
        "applicable": applicable,
        "reason": reason,
    }


def _summarize(items, describe, limit=5):
    """First `limit` items joined for a reason string; says how many more were left out."""
    text = "; ".join(describe(item) for item in items[:limit])
    return text + (f"; +{len(items) - limit} more ({len(items)} in total)" if len(items) > limit else "")


def _requirements_lines(root):
    req = root / "requirements.txt"
    if not req.is_file():
        return None
    lines = [ln.strip() for ln in req.read_text(encoding="utf-8", errors="replace").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith(("#", "-"))]


def _gitignore_covers(root, names):
    """True if some .gitignore line ignores one of `names` (ignoring slashes and a trailing *)."""
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return False
    for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        entry = line.strip().strip("/").rstrip("*")
        if entry in names:
            return True
    return False


def _run_command_documented(readme_text):
    for heading, body in tools._split_sections(readme_text):
        if ("run" in heading or "usage" in heading) and "```" in body:
            return True
    return False


# --- one function per criterion --------------------------------------------- #
def _reproducibility(root, readme_text, manifest):
    checks = [
        _check(
            "manifest_present", "reproducibility", manifest["has_manifest"],
            "Dependency manifest found: " + ", ".join(manifest["manifests_found"])
            if manifest["has_manifest"] else "No dependency manifest (requirements.txt, package.json, ...).",
        ),
        _check(
            "env_example_present", "reproducibility", manifest["has_env_example"],
            ".env.example present." if manifest["has_env_example"] else "Missing .env.example.",
        ),
    ]
    lines = _requirements_lines(root)
    if lines is None:
        checks.append(_check("deps_pinned", "reproducibility", True,
                             "Only requirements.txt is checked for pinning.", applicable=False))
    else:
        unpinned = [ln for ln in lines if "==" not in ln]
        checks.append(_check(
            "deps_pinned", "reproducibility", not unpinned,
            "All requirements are pinned with ==." if not unpinned
            else "Unpinned requirements: " + ", ".join(unpinned[:5]),
        ))
    is_python = lines is not None or (root / "pyproject.toml").is_file()
    states_version = bool(re.search(r"python\s*3\.\d+|python_requires|requires-python", readme_text, re.I))
    checks.append(_check(
        "python_version_stated", "reproducibility", states_version,
        "README states the Python version." if states_version else "README does not state the Python version.",
        applicable=is_python,
    ))
    has_run = _run_command_documented(readme_text)
    checks.append(_check(
        "run_command_documented", "reproducibility", has_run,
        "A run/usage section contains a command." if has_run else "No run/usage section with a code block.",
    ))
    return checks


def _documentation(path, readme_text):
    if not readme_text:
        return [_check("readme_present", "documentation", False, "Missing README.md.")]
    sections = tools.check_readme_sections(path)
    quality = tools.check_readme_quality(path)
    links = check_links(path)
    return [
        _check("readme_present", "documentation", True, "README.md present."),
        _check(
            "sections_present", "documentation", not sections["missing_sections"],
            "All required sections present." if not sections["missing_sections"]
            else "Missing sections: " + ", ".join(sections["missing_sections"]),
        ),
        _check(
            "no_placeholders", "documentation", not sections["placeholders_left"],
            "No template placeholders left." if not sections["placeholders_left"]
            else "Unfilled placeholders: " + ", ".join(sections["placeholders_left"]),
        ),
        _check(
            "sections_not_thin", "documentation", not quality["thin_sections"],
            "No thin sections." if not quality["thin_sections"]
            else "Thin sections: " + ", ".join(quality["thin_sections"]),
        ),
        _check(
            "commands_reference_real_files", "documentation", not quality["missing_referenced_files"],
            "Commands only reference files that exist." if not quality["missing_referenced_files"]
            else "Commands reference missing files: " + ", ".join(quality["missing_referenced_files"]),
        ),
        _check("links_ok", "documentation", links["passed"], links["reason"]),
    ]


def _security(path, root):
    secrets = tools.scan_for_secrets(path)
    risky = tools.check_risky_code(path)
    covers = {
        ".env": _gitignore_covers(root, {".env"}),
        "virtualenv": _gitignore_covers(root, {".venv", "venv", "env"}),
        "__pycache__": _gitignore_covers(root, {"__pycache__"}),
    }
    missing = [name for name, ok in covers.items() if not ok]
    found = secrets["findings"]
    return [
        _check(
            "no_secrets", "security", not found,
            "No secrets, .env files or virtualenvs outside git ignore." if not found
            else _summarize(found, lambda f: f"{f['file']}: {f['issue']}"),
        ),
        _check(
            "gitignore_covers_secrets_and_venv", "security", not missing,
            ".gitignore covers .env, virtualenvs and __pycache__." if not missing
            else ".gitignore does not cover: " + ", ".join(missing),
        ),
        _check(
            "no_risky_code", "security", risky["clean"],
            "No shell/eval patterns found." if risky["clean"]
            else _summarize(risky["findings"], lambda f: f"{f['file']}:{f['line']} {f['issue']}"),
        ),
    ]


def _scope(path):
    name = tools.check_folder_name(path)
    if os.getenv("PR_SCOPE", "on").strip().lower() == "off":
        pr = {"applicable": False, "reason": "PR scope check disabled (PR_SCOPE=off)."}
    else:
        pr = tools.check_pr_scope(path)
    name_ok = name["is_kebab_case"] and not name["is_generic"]
    checks = [_check(
        "folder_name_ok", "scope", name_ok,
        f"'{name['name']}' is lowercase kebab-case and not generic." if name_ok
        else f"'{name['name']}' must be lowercase kebab-case and not a generic name.",
    )]
    if not pr["applicable"]:
        checks.append(_check("pr_scope", "scope", True, pr["reason"], applicable=False))
    elif pr["project_files_changed"] == 0:
        checks.append(_check("pr_scope", "scope", True,
                             "This folder has no changes in the PR, so PR scope is not checked.", applicable=False))
    else:
        checks.append(_check(
            "pr_scope", "scope", pr["within_scope"],
            "Changes stay in the project folder plus at most one index row." if pr["within_scope"]
            else f"Files outside the project: {pr['files_outside_project']}; index rows added: {pr['index_rows_added']}.",
        ))
    return checks


def run_deterministic_checks(path: str, criteria=None) -> dict:
    """Run deterministic checks and return pass/fail results with short reasons.

    Args:
        path: Folder name or path of the project to review.
        criteria: Optional list of criteria to run; default is all four.
    """
    root, err = tools._check_dir(path)
    if err:
        return err
    wanted = list(criteria) if criteria else CRITERIA
    unknown = [c for c in wanted if c not in CRITERIA]
    if unknown:
        return {"error": f"Unknown criteria: {unknown}. Use {CRITERIA}."}
    readme = root / "README.md"
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    builders = {
        "reproducibility": lambda: _reproducibility(root, readme_text, tools.check_manifest(path)),
        "documentation": lambda: _documentation(path, readme_text),
        "security": lambda: _security(path, root),
        "scope": lambda: _scope(path),
    }
    checks = [check for criterion in wanted for check in builders[criterion]()]
    return {"project": root.name, "checks": checks}

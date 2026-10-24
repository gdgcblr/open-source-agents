"""Deterministic contribution checks.

Each check inspects a project folder (e.g. ``agents/my-project``) and returns a
plain dict, so it can be used directly from the CLI, from tests, or as a tool
by the ADK agent. Nothing here executes code from the reviewed project.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ALLOWED_PARENTS = ("agents", "tools")
KEBAB_CASE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
GENERIC_NAMES = {
    "my-agent", "my-tool", "my-project", "final-project", "project", "test",
    "tests", "demo", "agent", "tool", "sample", "example", "untitled",
}
MANIFESTS = (
    "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
    "package.json", "go.mod", "Cargo.toml",
)

# Headings that template/README.md asks every contribution to fill in.
REQUIRED_README_SECTIONS = (
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
    "License",
)

# Text that only appears if a template section was copied but never edited.
TEMPLATE_PLACEHOLDERS = (
    "[Project Name]",
    "[One-sentence summary",
    "Explain what specific problem or challenge this project addresses",
    "Feature 1: Brief description of the capability",
    "[Language Runtime, e.g., Python 3.10+ or Node.js 18+]",
    "[Required API keys or service accounts]",
    "Specify the license for this subproject",
    "Be honest about constraints, edge cases, and failure modes",
)

SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "OpenAI API key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}"),
    "GitHub token": re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}

# Files and folders that must never be committed.
FORBIDDEN_FILE_NAMES = {".env", "credentials.json", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
FORBIDDEN_DIRS = {".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache"}

MAX_SCAN_BYTES = 1_000_000


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def find_repo_root(start: Path) -> Path | None:
    out = _run_git(["rev-parse", "--show-toplevel"], start if start.is_dir() else start.parent)
    return Path(out.strip()).resolve() if out else None


def resolve_project(project_path: str) -> tuple[Path, Path | None]:
    """Resolve a project path given relative to the cwd or to the repo root."""
    candidate = Path(project_path).expanduser()
    if not candidate.is_absolute() and not candidate.exists():
        root = find_repo_root(Path.cwd())
        if root and (root / candidate).exists():
            candidate = root / candidate
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise FileNotFoundError(f"Project folder not found: {project_path}")
    return candidate, find_repo_root(candidate)


def _project_files(project: Path, repo_root: Path | None) -> list[Path]:
    """Files that would be committed: tracked or untracked-but-not-ignored.

    Falls back to walking the folder (skipping dependency dirs) outside git.
    """
    if repo_root:
        out = _run_git(
            ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", str(project)],
            repo_root,
        )
        if out is not None:
            return sorted({(repo_root / p).resolve() for p in out.split("\0") if p})
    return sorted(
        p for p in project.rglob("*")
        if p.is_file() and not (FORBIDDEN_DIRS & set(p.relative_to(project).parts[:-1]))
        and ".git" not in p.parts
    )


def _redact(value: str) -> str:
    return value[:4] + "…" + f"({len(value)} chars)"


def check_structure(project_path: str) -> dict:
    """Check folder location, kebab-case naming and the required files.

    Args:
        project_path: Path to the contribution folder, e.g. "agents/my-project".

    Returns:
        A dict with "passed" (bool), "issues" (list of problems) and "details".
    """
    project, _ = resolve_project(project_path)
    issues: list[str] = []
    name, parent = project.name, project.parent.name

    if parent not in ALLOWED_PARENTS:
        issues.append(f"Folder must live directly under agents/ or tools/, found under '{parent}/'.")
    if not KEBAB_CASE.match(name):
        issues.append(f"Folder name '{name}' is not lowercase kebab-case.")
    if name in GENERIC_NAMES:
        issues.append(f"Folder name '{name}' is too generic; use a name describing what it does.")

    present = {p.name for p in project.iterdir()}
    for required in ("README.md", ".gitignore", ".env.example"):
        if required not in present:
            issues.append(f"Missing required file: {required}")
    manifests = [m for m in MANIFESTS if m in present]
    if not manifests:
        issues.append("No dependency manifest found (requirements.txt, pyproject.toml, package.json, ...).")

    return {
        "check": "structure",
        "passed": not issues,
        "issues": issues,
        "details": {"folder": f"{parent}/{name}", "manifests": manifests},
    }


def check_readme(project_path: str) -> dict:
    """Check that README.md has every template section and no leftover placeholders.

    Args:
        project_path: Path to the contribution folder, e.g. "agents/my-project".

    Returns:
        A dict with "passed", "issues", and "details" listing missing sections
        and template placeholders that were never replaced.
    """
    project, _ = resolve_project(project_path)
    readme = project / "README.md"
    if not readme.is_file():
        return {"check": "readme", "passed": False, "issues": ["README.md is missing."], "details": {}}

    text = readme.read_text(encoding="utf-8", errors="replace")
    headings = {
        re.sub(r"\s+", " ", m.group(1)).strip().lower()
        for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE)
    }
    missing = [s for s in REQUIRED_README_SECTIONS if not any(s.lower() in h for h in headings)]
    # Quoting a placeholder inside a fenced code block (e.g. sample output) is fine.
    prose = re.sub(r"^(```|~~~).*?^\1", "", text, flags=re.MULTILINE | re.DOTALL)
    placeholders = [p for p in TEMPLATE_PLACEHOLDERS if p in prose]

    issues = [f"Missing README section: {s}" for s in missing]
    issues += [f"Template placeholder not replaced: \"{p}\"" for p in placeholders]
    return {
        "check": "readme",
        "passed": not issues,
        "issues": issues,
        "details": {"missing_sections": missing, "placeholders": placeholders, "length_chars": len(text)},
    }


def scan_secrets(project_path: str) -> dict:
    """Scan files that would be committed for secrets and forbidden files.

    Matches are redacted, so secret values never leave this function.

    Args:
        project_path: Path to the contribution folder, e.g. "agents/my-project".

    Returns:
        A dict with "passed", "issues", and "details" with the scanned file count.
    """
    project, repo_root = resolve_project(project_path)
    files = _project_files(project, repo_root)
    issues: list[str] = []

    for path in files:
        rel = path.relative_to(project).as_posix()
        parts = set(path.relative_to(project).parts[:-1])
        if path.name in FORBIDDEN_FILE_NAMES or path.name.startswith(".env.") and path.name != ".env.example":
            issues.append(f"Secret/config file would be committed: {rel}")
        elif path.suffix in FORBIDDEN_SUFFIXES or path.name.startswith("service-account"):
            issues.append(f"Key/credential file would be committed: {rel}")
        if parts & FORBIDDEN_DIRS:
            issues.append(f"Dependency/cache folder would be committed: {rel}")
            continue
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable
        for label, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                issues.append(f"Possible {label} in {rel}:{line} ({_redact(match.group(0))})")

    return {
        "check": "secrets",
        "passed": not issues,
        "issues": issues,
        "details": {"files_scanned": len(files), "uses_git_index": repo_root is not None},
    }


def check_scope(project_path: str, base_ref: str = "upstream/main") -> dict:
    """Check that the branch only changes files inside the project folder.

    Changes to agents/README.md or tools/README.md (the index tables) are allowed.

    Args:
        project_path: Path to the contribution folder, e.g. "agents/my-project".
        base_ref: Git ref the PR will merge into, e.g. "upstream/main" or "origin/main".

    Returns:
        A dict with "passed", "issues", and "details" listing changed files.
    """
    project, repo_root = resolve_project(project_path)
    if not repo_root:
        return {"check": "scope", "passed": True, "issues": [],
                "details": {"skipped": "Not inside a git repository."}}

    committed = _run_git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root)
    if committed is None:
        return {"check": "scope", "passed": True, "issues": [],
                "details": {"skipped": f"Could not diff against '{base_ref}'. Fetch it or pass another base ref."}}
    pending = _run_git(["status", "--porcelain", "--untracked-files=all"], repo_root) or ""
    changed = set(committed.split()) | {line[3:].strip().strip('"') for line in pending.splitlines() if line}

    project_rel = project.relative_to(repo_root).as_posix() + "/"
    allowed_index = {f"{p}/README.md" for p in ALLOWED_PARENTS}
    outside = sorted(f for f in changed if f and not f.startswith(project_rel) and f not in allowed_index)

    return {
        "check": "scope",
        "passed": not outside,
        "issues": [f"Change outside the project folder: {f}" for f in outside],
        "details": {"base_ref": base_ref, "changed_files": len(changed)},
    }


def read_readme(project_path: str) -> dict:
    """Return the README.md text (truncated to 20,000 chars) for a quality review.

    Args:
        project_path: Path to the contribution folder, e.g. "agents/my-project".

    Returns:
        A dict with "content" and "truncated".
    """
    project, _ = resolve_project(project_path)
    readme = project / "README.md"
    if not readme.is_file():
        return {"content": "", "truncated": False}
    text = readme.read_text(encoding="utf-8", errors="replace")
    return {"content": text[:20_000], "truncated": len(text) > 20_000}


def run_all_checks(project_path: str, base_ref: str = "upstream/main") -> list[dict]:
    return [
        check_structure(project_path),
        check_readme(project_path),
        scan_secrets(project_path),
        check_scope(project_path, base_ref),
    ]


def format_report(results: list[dict]) -> str:
    lines = []
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        skipped = r.get("details", {}).get("skipped")
        lines.append(f"[{'SKIP' if skipped else status}] {r['check']}" + (f" - {skipped}" if skipped else ""))
        lines += [f"    - {issue}" for issue in r["issues"]]
    verdict = "Ready for review" if all(r["passed"] for r in results) else "Needs changes"
    lines.append(f"\nVerdict: {verdict}")
    return "\n".join(lines)

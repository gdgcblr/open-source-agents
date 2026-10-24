#!/usr/bin/env python3
"""Audits a contribution under agents/ or tools/ against this repo's CONTRIBUTING.md standards.

Runs cheap static checks (naming, manifest, .gitignore, secret scanning, README section
coverage, scope isolation) and, unless --no-llm is passed, asks Claude to read the README
and the static findings and render judgment the static checks can't: whether the examples
look genuine, whether limitations are honestly disclosed, and an overall verdict.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

DEFAULT_MODEL = os.environ.get("MODEL_NAME", "claude-sonnet-4-5-20250929")

REQUIRED_README_SECTIONS = [
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

MANIFEST_FILES = ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]

DISALLOWED_NAMES = {"my-agent", "my-tool", "final-project", "final-test", "test", "demo", "helper"}

SECRET_FILENAME_PATTERNS = [
    re.compile(r"^\.env$"),
    re.compile(r"^\.env\.(?!example$).+$"),
    re.compile(r".*\.pem$"),
    re.compile(r".*\.key$"),
    re.compile(r"^credentials\.json$"),
    re.compile(r"^service-account.*\.json$"),
]

SECRET_CONTENT_PATTERNS = {
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Anthropic-style API key": re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"),
    "OpenAI-style API key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "Private key block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Hardcoded password assignment": re.compile(r"(?i)password\s*[=:]\s*['\"][^'\"]{4,}['\"]"),
}

SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__"}


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(out.stdout.strip())


def list_files(root: Path, target: Path) -> list[Path]:
    """Root-relative paths for everything under target: git-tracked files if any exist,
    otherwise a plain filesystem walk (so a contribution can be audited before it's staged)."""
    rel = target.relative_to(root)
    out = subprocess.run(
        ["git", "ls-files", str(rel)], capture_output=True, text=True, check=True, cwd=root
    )
    tracked = [Path(p) for p in out.stdout.splitlines() if p]
    if tracked:
        return tracked

    found = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            found.append((Path(dirpath) / fn).relative_to(root))
    return found


def check_naming(target: Path) -> list[str]:
    name = target.name
    issues = []
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        issues.append(f"Directory name '{name}' is not lowercase kebab-case.")
    if name in DISALLOWED_NAMES:
        issues.append(f"Directory name '{name}' is a disallowed generic placeholder name.")
    return issues


def check_manifest(files: list[Path]) -> list[str]:
    names = {f.name for f in files}
    if not any(m in names for m in MANIFEST_FILES):
        return [f"No dependency manifest found (expected one of: {', '.join(MANIFEST_FILES)})."]
    return []


def check_gitignore(target: Path) -> list[str]:
    if not (target / ".gitignore").exists():
        return ["No .gitignore present in the project directory."]
    return []


def check_secrets(root: Path, files: list[Path]) -> list[str]:
    issues = []
    for rel in files:
        if any(p.match(rel.name) for p in SECRET_FILENAME_PATTERNS):
            issues.append(f"Tracked file looks like a secret by name: {rel}")
            continue
        full = root / rel
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_CONTENT_PATTERNS.items():
            if pattern.search(text):
                issues.append(f"Possible {label} found in tracked file: {rel}")
    return issues


def check_readme_sections(target: Path) -> tuple[list[str], str]:
    readme = target / "README.md"
    if not readme.exists():
        return (["README.md is missing entirely."], "")
    text = readme.read_text(encoding="utf-8", errors="ignore")
    headings = re.findall(r"^#{1,3}\s+(.+?)\s*$", text, re.MULTILINE)
    missing = [
        s for s in REQUIRED_README_SECTIONS if not any(s.lower() in h.lower() for h in headings)
    ]
    return [f"README is missing the '{s}' section." for s in missing], text


def check_scope(root: Path, target: Path, base: str | None) -> list[str]:
    if not base:
        return []
    rel = target.relative_to(root)
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True, text=True, cwd=root,
    )
    changed = [Path(p) for p in out.stdout.splitlines() if p]
    allowed_index_files = {Path("agents/README.md"), Path("tools/README.md")}
    outside = [p for p in changed if rel not in p.parents and p not in allowed_index_files]
    return [f"Change touches file outside the project directory: {p}" for p in outside]


def run_llm_review(project: str, readme_text: str, findings: list[str], model: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "(Skipped: ANTHROPIC_API_KEY is not set.)"

    findings_block = "\n".join(f"- {f}" for f in findings) or "- None found by static checks."

    system = """You are auditing a contribution to an open-source catalog of AI agents and tools.
Judge it against these four criteria from the repo's CONTRIBUTING.md:
1. Reproducibility - clear prerequisites, dependencies, setup steps that would work from scratch.
2. Documentation Quality - uses the required template sections, with realistic (not vague or
   clearly fabricated-looking) examples.
3. Security & Privacy - no committed secrets, sensible .env handling, honest disclosure of what
   data leaves the system.
4. Focused Scope - self-contained, does not touch unrelated files.

You are given the automated static-check findings and the project's full README. Add judgment
the static checks cannot make: cross-check the README's claims for plausibility, flag vague or
fabricated-looking examples, and note any limitations that are glossed over or missing.

Respond with exactly three parts:
1. A one-line verdict: PASS, NEEDS WORK, or FAIL.
2. The most important issues to fix, ranked by importance (skip this if there are none).
3. Anything done well, if genuinely true (skip this if nothing stands out).
Be concise and specific. Do not restate the static findings verbatim."""

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"Project directory: {project}\n\n"
                f"Static check findings:\n{findings_block}\n\n"
                f"README.md contents:\n{readme_text[:20000]}"
            ),
        }],
    )
    return "".join(b.text for b in message.content if b.type == "text")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit a contribution against this repo's CONTRIBUTING.md standards."
    )
    parser.add_argument("path", help="Path to the contribution directory, e.g. agents/my-agent")
    parser.add_argument("--base", help="Base git ref to diff against for scope checking, e.g. origin/main")
    parser.add_argument("--no-llm", action="store_true", help="Skip the Claude review; static checks only.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model to use (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    target = Path(args.path).resolve()
    root = repo_root()
    if not target.is_dir():
        print(f"Not a directory: {target}", file=sys.stderr)
        sys.exit(1)
    try:
        rel_target = target.relative_to(root)
    except ValueError:
        print(f"{target} is not inside the git repo at {root}", file=sys.stderr)
        sys.exit(1)

    files = list_files(root, target)
    if not files:
        print(f"No files found under {rel_target}.", file=sys.stderr)
        sys.exit(1)

    findings: list[str] = []
    findings += check_naming(target)
    findings += check_manifest(files)
    findings += check_gitignore(target)
    findings += check_secrets(root, files)
    readme_issues, readme_text = check_readme_sections(target)
    findings += readme_issues
    findings += check_scope(root, target, args.base)

    print(f"## Static checks for {rel_target}\n")
    if findings:
        for f in findings:
            print(f"- [ ] {f}")
    else:
        print("- No static issues found.")

    if not args.no_llm:
        print("\n## Claude review\n")
        print(run_llm_review(str(rel_target), readme_text, findings, args.model))


if __name__ == "__main__":
    main()

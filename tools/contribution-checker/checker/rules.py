import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

GENERIC = {"my-agent", "my-tool", "test", "demo", "helper", "final-project", "final-test"}
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
README_SECTIONS = ["Overview", "Technical Stack", "Prerequisites", "Installation",
                   "How to Run", "Example Input", "How to Test",
                   "Known Limitations", "Security"]
MANIFESTS = ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]
PLACEHOLDERS = ["[Project Name]", "[One-sentence summary", "<project-slug>"]

@dataclass
class Result:
    rule: str
    passed: bool
    message: str
    fix: str = ""

def check_location(p: Path) -> Result:
    ok = p.parent.name in ("agents", "tools")
    return Result("location", ok, f"Parent folder is '{p.parent.name}'",
                  "" if ok else "Move the project under agents/ or tools/")

def check_name(p: Path) -> Result:
    ok = bool(KEBAB.match(p.name)) and p.name not in GENERIC
    return Result("folder-name", ok, f"Folder name: '{p.name}'",
                  "" if ok else "Use a descriptive lowercase kebab-case name")

def check_required_files(p: Path) -> Result:
    missing = [f for f in ("README.md", ".env.example", ".gitignore") if not (p / f).exists()]
    if not any((p / m).exists() for m in MANIFESTS):
        missing.append("dependency manifest")
    return Result("required-files", not missing,
                  "All required files present" if not missing else f"Missing: {', '.join(missing)}",
                  "" if not missing else "Add the missing files (copy from template/)")

def check_readme(p: Path) -> Result:
    f = p / "README.md"
    if not f.exists():
        return Result("readme", False, "README.md not found", "Copy template/README.md")
    text = f.read_text(encoding="utf-8", errors="ignore")
    missing = [s for s in README_SECTIONS if s.lower() not in text.lower()]
    left = [x for x in PLACEHOLDERS if x in text]
    ok = not missing and not left
    msg = "README complete" if ok else f"Missing sections: {missing}; placeholders: {left}"
    return Result("readme", ok, msg, "" if ok else "Fill all template sections, remove placeholders")

def check_tracked_junk(p: Path) -> Result:
    try:
        out = subprocess.run(["git", "ls-files", str(p)], capture_output=True, text=True, check=True).stdout
    except Exception:
        return Result("tracked-files", True, "Skipped (not a git repo)")
    bad = [l for l in out.splitlines()
           if l.endswith("/.env") or l == ".env" or "/.venv/" in l
           or "node_modules/" in l or l.endswith(".db")]
    return Result("tracked-files", not bad,
                  "No forbidden files tracked" if not bad else f"Tracked: {bad}",
                  "" if not bad else "git rm --cached these files and add them to .gitignore")

def check_scope(p: Path, base: str = "upstream/main") -> Result:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True, text=True, check=True, cwd=p).stdout
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, cwd=p).stdout.strip()
    except Exception:
        return Result("scope", True, f"Skipped (no git history against {base})")
    rel = p.resolve().relative_to(Path(top).resolve()).as_posix()
    index = f"{p.parent.name}/README.md"
    outside = [f for f in out.splitlines()
               if not f.startswith(rel + "/") and f != index]
    return Result("scope", not outside,
                  "Changes confined to project folder" if not outside
                  else f"Files outside your folder: {outside}",
                  "" if not outside else "Revert changes to unrelated files")

def run_all(p: Path) -> list[Result]:
    from .secrets import check_secrets
    return [check_location(p), check_name(p), check_required_files(p),
            check_readme(p), check_tracked_junk(p), check_secrets(p),
            check_scope(p)]
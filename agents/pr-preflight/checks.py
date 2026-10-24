"""Stage 1: deterministic contribution-standard checks (no LLM involved).

Usage: python checks.py <project_path>
"""
import fnmatch
import os
import re
import sys
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google API keys
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
]
SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__"}
JUNK_DIRS = {".venv", "venv", "node_modules", "__pycache__"}
REQUIRED = ["README.md", ".env.example", ".gitignore"]
MANIFESTS = ["requirements.txt", "package.json", "pyproject.toml"]
MAX_SCAN_BYTES = 1_000_000


def mask(value: str) -> str:
    return value[:4] + "****"


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def is_env_file(name: str) -> bool:
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def gitignore_patterns(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.is_file():
        return []
    lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def is_ignored(rel: str, is_dir: bool, patterns: list[str]) -> bool:
    """Small .gitignore matcher: globs, trailing '/', leading '/', '!' negation."""
    name = rel.rsplit("/", 1)[-1]
    ignored = False
    for pat in patterns:
        negate = pat.startswith("!")
        p = pat[1:] if negate else pat
        if p.endswith("/"):
            if not is_dir:
                continue
            p = p[:-1]
        p = p.lstrip("/")
        target = rel if "/" in p else name
        if fnmatch.fnmatch(target, p):
            ignored = not negate
    return ignored


def walk(root: Path):
    """Yield (relative_posix_path, is_dir) for everything outside SKIP_DIRS.

    Skipped dirs are still yielded once (so JUNK can see them) but not entered.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for d in list(dirnames):
            rel = (base / d).relative_to(root).as_posix()
            yield rel, True
            if d in SKIP_DIRS:
                dirnames.remove(d)
        for f in filenames:
            yield (base / f).relative_to(root).as_posix(), False


def check_required(root: Path) -> dict:
    missing = [f for f in REQUIRED if not (root / f).is_file()]
    if not any((root / m).is_file() for m in MANIFESTS):
        missing.append(" / ".join(MANIFESTS))
    if missing:
        return {"id": "REQUIRED_FILES", "status": "fail",
                "message": "Missing: " + ", ".join(missing),
                "fix": "Add the missing files (see the repo contribution guide)."}
    return {"id": "REQUIRED_FILES", "status": "pass",
            "message": "All required files present.", "fix": ""}


def scan_file(path: Path, rel: str) -> list[str]:
    data = path.read_bytes()[:MAX_SCAN_BYTES]
    if b"\0" in data:  # binary file
        return []
    findings = []
    for lineno, line in enumerate(data.decode("utf-8", "ignore").splitlines(), 1):
        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(line):
                findings.append(f"{rel}:{lineno} {mask(m.group())}")
    return findings


def check_secrets(root: Path, patterns: list[str]) -> dict:
    findings, notes = [], []
    for rel, is_dir in walk(root):
        name = rel.rsplit("/", 1)[-1]
        if is_dir or name == ".env.example":
            continue
        if is_env_file(name):  # never opened
            if is_ignored(rel, False, patterns):
                notes.append(f"{rel} present but gitignored (OK)")
            else:
                findings.append(f"{rel} is a secrets file and is NOT gitignored")
            continue
        try:
            findings += scan_file(root / rel, rel)
        except OSError:
            continue
    if findings:
        return {"id": "SECRETS", "status": "fail", "message": "; ".join(findings),
                "fix": "Remove the secret, rotate the key, load it from .env, "
                       "and make sure .env is in .gitignore."}
    msg = "No secrets found." + (" " + "; ".join(notes) if notes else "")
    return {"id": "SECRETS", "status": "pass", "message": msg, "fix": ""}


def check_junk(root: Path, patterns: list[str]) -> dict:
    bad = [rel for rel, is_dir in walk(root)
           if is_dir and rel.rsplit("/", 1)[-1] in JUNK_DIRS
           and not is_ignored(rel, True, patterns)]
    if bad:
        return {"id": "JUNK", "status": "fail",
                "message": "Not gitignored: " + ", ".join(bad),
                "fix": "Add these to .gitignore: " + ", ".join(
                    sorted({b.rsplit('/', 1)[-1] + '/' for b in bad}))}
    return {"id": "JUNK", "status": "pass", "message": "No un-ignored junk folders.", "fix": ""}


def run_checks(project_path: str) -> list[dict]:
    root = Path(project_path).resolve()
    patterns = gitignore_patterns(root)
    return [check_required(root), check_secrets(root, patterns), check_junk(root, patterns)]


def print_results(results: list[dict]) -> None:
    for r in results:
        icon = "✅" if r["status"] == "pass" else "❌"
        print(f"{icon} {r['id']}: {r['message']}")
        if r["fix"]:
            print(f"   fix: {r['fix']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        sys.exit("usage: python checks.py <project_path>")
    res = run_checks(sys.argv[1])
    print_results(res)
    sys.exit(1 if any(r["status"] == "fail" for r in res) else 0)

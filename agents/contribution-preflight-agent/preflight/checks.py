import re
from pathlib import Path

from .rules import Rules

KEBAB_CASE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SKIP_DIRS = {"reports", ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".pytest_cache", "dist", "build"}
FORBIDDEN_FILES = (".env", "credentials.json")
FORBIDDEN_SUFFIXES = (".pem", ".key")
SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
MAX_SCAN_BYTES = 1_000_000
MAX_DOC_CHARS = 12_000


def _walk(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def _result(findings: list[str]) -> dict:
    return {"status": "fail" if findings else "pass", "findings": findings}


def check_structure(project_path: str, rules: Rules) -> dict:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return {"status": "error", "findings": [f"Not a directory: {project_path}"]}
    findings = []
    name = root.name
    if rules.kebab_case and not KEBAB_CASE.match(name):
        findings.append(f"Directory name '{name}' is not lowercase kebab-case.")
    if name in rules.forbidden_names:
        findings.append(f"Directory name '{name}' is too generic.")
    for required in rules.required_files:
        if not (root / required).is_file():
            findings.append(f"Missing required file: {required}")
    if rules.manifest_any_of and not any((root / manifest).is_file() for manifest in rules.manifest_any_of):
        findings.append("No dependency manifest found (" + ", ".join(rules.manifest_any_of) + ").")
    readme = root / "README.md"
    if readme.is_file():
        text = CODE_FENCE.sub("", readme.read_text(encoding="utf-8", errors="replace"))
        for marker in rules.template_markers:
            if marker in text:
                findings.append(f"README still contains template placeholder text: {marker}")
    return _result(findings)


def check_security(project_path: str) -> dict:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return {"status": "error", "findings": [f"Not a directory: {project_path}"]}
    findings = []
    for path in _walk(root):
        rel = path.relative_to(root).as_posix()
        if path.name in FORBIDDEN_FILES or path.suffix in FORBIDDEN_SUFFIXES or path.name.startswith("service-account"):
            findings.append(f"Secret-bearing file must not be committed: {rel}")
            continue
        if path.name.startswith(".env.") and path.name != ".env.example":
            findings.append(f"Env file must not be committed: {rel}")
            continue
        if path.stat().st_size > MAX_SCAN_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"Possible {label} in {rel}")
    return _result(findings)


def collect_docs(project_path: str) -> dict:
    root = Path(project_path).resolve()
    readme = root / "README.md"
    if not readme.is_file():
        return {"status": "error", "readme": "", "files": []}
    text = readme.read_text(encoding="utf-8", errors="replace")[:MAX_DOC_CHARS]
    files = [path.relative_to(root).as_posix() for path in _walk(root)][:100]
    return {"status": "ok", "readme": text, "files": files}

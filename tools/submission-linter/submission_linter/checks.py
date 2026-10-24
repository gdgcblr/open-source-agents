"""Deterministic checks that encode the open-source-ai contribution rules."""

from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import ERROR, INFO, WARN, Report
from .secrets_scan import scan_text

CATEGORIES = ("agents", "tools")
GENERIC_NAMES = {
    "my-agent", "my-tool", "final-project", "final-test", "test", "demo", "helper",
    "project", "agent", "tool", "untitled", "temp", "sample", "example", "new-project",
}
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".idea", ".vscode", ".next",
}
SECRET_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development", "id_rsa", "id_ed25519",
    "credentials.json", "service-account.json", "service_account.json",
}
FORBIDDEN_SUFFIX_ERROR = (".pem", ".key", ".p12", ".pfx")
FORBIDDEN_SUFFIX_WARN = (".sqlite", ".sqlite3", ".db", ".pyc")
MANIFESTS = (
    "requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    "Gemfile", "pom.xml", "build.gradle", "deno.json",
)
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Cargo.lock"}
JS_EXT = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}

# (README heading keywords, display name). Missing => error.
REQUIRED_SECTIONS = [
    (("overview", "problem"), "Overview (Problem Statement & Intended Users)"),
    (("technical stack", "tech stack"), "Technical Stack"),
    (("prerequisite", "requirements"), "Prerequisites"),
    (("install", "setup"), "Installation & Setup"),
    (("configuration", "environment variable"), "Configuration & Environment Variables"),
    (("how to run", "usage", "running"), "How to Run"),
    (("example",), "Example Input & Output"),
    (("how to test", "testing", "tests"), "How to Test"),
    (("limitation",), "Known Limitations"),
    (("security", "privacy"), "Security & Privacy Considerations"),
]
# Missing => warning.
RECOMMENDED_SECTIONS = [
    (("architecture", "data flow"), "Architecture & Data Flow"),
    (("future",), "Future Improvements"),
    (("license",), "License"),
]

# Text copied verbatim from template/README.md that must be replaced.
TEMPLATE_PHRASES = [
    "[Project Name]",
    "[One-sentence summary",
    "Feature 1: Brief description",
    "Feature 2: Brief description",
    "[Language Runtime",
    "[Package manager",
    "[Required API keys",
    "gdgcblr/open-source-agents",
    "Rate limits on free-tier APIs may cause retries to fail",
    "Currently only tested on text files smaller than 10MB",
    "Does not maintain conversation memory across separate process restarts",
    "Add caching for external API responses",
    "Explain what specific problem or challenge this project addresses",
    "Specify the license for this subproject",
    "Analysis completed:",
    "Summarize the latest release notes",
    "API key for the primary LLM provider",
]

# Variables that are standard OS/runtime knobs and need no documentation.
COMMON_ENV = {
    "PATH", "HOME", "USER", "PWD", "SHELL", "LANG", "TERM", "TMPDIR", "TEMP", "TMP",
    "NODE_ENV", "CI", "PYTHONPATH", "VIRTUAL_ENV", "NO_COLOR", "PORT", "HOST",
}
ENV_PATTERNS = [
    re.compile(r"""os\.getenv\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.environ\.get\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.environ\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]"""),
    re.compile(r"""process\.env\.([A-Za-z_][A-Za-z0-9_]*)"""),
    re.compile(r"""process\.env\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]"""),
    re.compile(r"""os\.Getenv\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)"""),
    re.compile(r"""env::var\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)"""),
]
# import name -> distribution name, where they differ.
IMPORT_ALIASES = {
    "yaml": "pyyaml", "PIL": "pillow", "dotenv": "python-dotenv", "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn", "cv2": "opencv-python", "dateutil": "python-dateutil",
    "jwt": "pyjwt", "git": "gitpython", "attr": "attrs", "serial": "pyserial",
    "mcp": "mcp", "fitz": "pymupdf", "docx": "python-docx", "pptx": "python-pptx",
}
SKIP_IMPORTS = {"google", "__future__"}  # google.* is a namespace shared by many dists


# --------------------------------------------------------------------------- helpers


class GitError(RuntimeError):
    pass


def git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(str(exc)) from exc
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def read_text(path: Path, limit: int = 1_000_000) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > limit or b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


@dataclass
class FileListing:
    files: list[Path]
    used_git: bool
    local_only: list[str]  # secret-ish dirs found on disk when git is unavailable


def list_files(project: Path) -> FileListing:
    """Files that would be part of a commit (respects .gitignore when git is available)."""
    try:
        git(["rev-parse", "--show-toplevel"], project)
        out = git(["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "."], project)
        files = [project / p for p in out.split("\0") if p]
        return FileListing([f for f in files if f.is_file()], True, [])
    except GitError:
        pass
    files: list[Path] = []
    local_only: list[str] = []
    for root, dirs, names in os.walk(project):
        for d in list(dirs):
            if d in SECRET_DIRS:
                local_only.append(str((Path(root) / d).relative_to(project)))
            if d in SKIP_DIRS:
                dirs.remove(d)
        files.extend(Path(root) / n for n in names)
    return FileListing(files, False, local_only)


def rel(path: Path, project: Path) -> str:
    return path.relative_to(project).as_posix()


@dataclass
class Section:
    level: int
    title: str
    line: int
    body: str


def parse_sections(text: str) -> list[Section]:
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    sections = []
    for idx, (i, level, title) in enumerate(heads):
        end = len(lines)
        for j, lv, _ in heads[idx + 1:]:
            if lv <= level:
                end = j
                break
        sections.append(Section(level, title, i + 1, "\n".join(lines[i + 1:end])))
    return sections


def find_section(sections: list[Section], keywords: tuple[str, ...]) -> Section | None:
    for s in sections:
        title = s.title.lower()
        if any(k in title for k in keywords):
            return s
    return None


def _is_empty(body: str) -> bool:
    stripped = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    if any(block.strip() for block in code_blocks(stripped)):
        return False  # a real command in a fenced block counts as content
    stripped = re.sub(r"[\s>*_`\-|#]", "", stripped)
    return len(stripped) < 15


def code_blocks(body: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"```[\w+-]*\n(.*?)```", body, flags=re.DOTALL)]


# --------------------------------------------------------------------------- checks


def check_location(project: Path, report: Report) -> str | None:
    category = project.parent.name
    slug = project.name
    if category not in CATEGORIES:
        report.add(
            ERROR, "LOC001",
            f"Project must live in agents/<slug>/ or tools/<slug>/ (found parent '{category}').",
            hint="Move the folder directly under agents/ or tools/.",
        )
        category = None
    if not KEBAB.match(slug):
        report.add(ERROR, "LOC002", f"Directory name '{slug}' is not lowercase kebab-case.",
                   hint="Use e.g. 'research-assistant'.")
    if slug in GENERIC_NAMES:
        report.add(ERROR, "LOC003", f"Directory name '{slug}' is too generic.",
                   hint="Name it after what it actually does.")
    if category in CATEGORIES:
        other = [c for c in CATEGORIES if c != category][0]
        if (project.parent.parent / other / slug).exists():
            report.add(WARN, "LOC004", f"A project named '{slug}' also exists in {other}/.",
                       hint="Pick a more specific name to avoid confusion.")
    return category


def check_required_files(project: Path, listing: FileListing, report: Report) -> None:
    present = {rel(f, project) for f in listing.files}
    for name in ("README.md", ".env.example", ".gitignore"):
        if name not in present:
            report.add(ERROR, "FIL001", f"Missing required file: {name}",
                       hint="Copy it from template/ (README.md, .gitignore, .env.example).")
    if not any(m in present for m in MANIFESTS):
        report.add(ERROR, "FIL002", "No dependency manifest found.",
                   hint=f"Add one of: {', '.join(MANIFESTS[:5])}, …")
    if not any(Path(p).suffix in {".py", ".go", ".rs", ".sh", ".java", ".rb"} | JS_EXT for p in present):
        report.add(WARN, "FIL003", "No source files detected in the project directory.")


def check_forbidden_files(project: Path, listing: FileListing, report: Report) -> None:
    flagged_dirs: set[str] = set()
    for f in listing.files:
        r = rel(f, project)
        parts = Path(r).parts
        for d in parts[:-1]:
            if d in SECRET_DIRS and d not in flagged_dirs:
                flagged_dirs.add(d)
                report.add(ERROR, "GIT001", f"'{d}/' would be committed.", path=r,
                           hint=f"Add '{d}/' to .gitignore and `git rm -r --cached {d}`.")
        name = f.name
        if name in FORBIDDEN_NAMES:
            report.add(ERROR, "GIT002", f"'{name}' must not be committed.", path=r,
                       hint="Add it to .gitignore; keep only .env.example.")
        elif name.endswith(FORBIDDEN_SUFFIX_ERROR):
            report.add(ERROR, "GIT003", f"Key/certificate file '{name}' would be committed.", path=r)
        elif name.endswith(FORBIDDEN_SUFFIX_WARN):
            report.add(WARN, "GIT004", f"'{name}' looks like a local database or build artifact.", path=r,
                       hint="Local databases and caches should not be tracked.")
    if not listing.used_git:
        gi = read_text(project / ".gitignore") or ""
        for d in listing.local_only:
            if d.split("/")[-1] not in gi:
                report.add(WARN, "GIT005", f"'{d}/' exists locally and is not in .gitignore.", path=d)
        for n in FORBIDDEN_NAMES:
            if (project / n).exists() and n not in gi:
                report.add(WARN, "GIT005", f"'{n}' exists locally and is not in .gitignore.", path=n)


def check_gitignore(project: Path, report: Report) -> None:
    text = read_text(project / ".gitignore")
    if text is None:
        return
    lines = {l.strip().rstrip("/") for l in text.splitlines()}
    if ".env" not in lines and ".env*" not in lines:
        report.add(WARN, "GIT006", ".gitignore does not ignore '.env'.", path=".gitignore")
    has_py = any(project.glob("*.py")) or (project / "requirements.txt").exists()
    if has_py and not ({".venv", "venv", "env"} & lines):
        report.add(WARN, "GIT006", ".gitignore does not ignore the virtual environment (.venv/).",
                   path=".gitignore")
    if (project / "package.json").exists() and "node_modules" not in lines:
        report.add(WARN, "GIT006", ".gitignore does not ignore node_modules/.", path=".gitignore")


def check_secrets(project: Path, listing: FileListing, report: Report) -> set[str]:
    """Return the set of relative paths that contain secrets (kept out of LLM review)."""
    tainted: set[str] = set()
    for f in listing.files:
        if f.name in LOCKFILES:
            continue
        text = read_text(f)
        if text is None:
            continue
        for hit in scan_text(text):
            r = rel(f, project)
            tainted.add(r)
            report.add(
                ERROR, "SEC001", f"Possible secret: {hit.label} ({hit.snippet})", path=r, line=hit.line,
                hint="Remove it, rotate the credential, and load it from an environment variable. "
                     "Add `# lint:allow-secret` on the line if it is a false positive.",
            )
    return tainted


def check_readme(project: Path, report: Report) -> tuple[str, list[Section]]:
    path = project / "README.md"
    text = read_text(path)
    if text is None:
        return "", []
    sections = parse_sections(text)
    for phrase in TEMPLATE_PHRASES:
        idx = text.find(phrase)
        if idx != -1:
            line = text.count("\n", 0, idx) + 1
            report.add(ERROR, "DOC001", f"Template text left unchanged: “{phrase}”", path="README.md",
                       line=line, hint="Replace every template placeholder with real content.")
    for m in re.finditer(r"^\s*[-*]?\s*\[[A-Z][^\]\n]{6,}\]\s*$", text, flags=re.MULTILINE):
        line = text.count("\n", 0, m.start()) + 1
        report.add(WARN, "DOC002", f"Bracketed placeholder still present: {m.group(0).strip()}",
                   path="README.md", line=line)
    missing = [name for keywords, name in REQUIRED_SECTIONS if find_section(sections, keywords) is None]
    if missing:
        report.add(ERROR, "DOC003", f"README is missing {len(missing)} required section(s): " + "; ".join(missing),
                   path="README.md",
                   hint="Copy the headings from template/README.md. Sections that do not apply may say 'N/A' with a short reason.")
    for keywords, name in REQUIRED_SECTIONS:
        sec = find_section(sections, keywords)
        if sec is None:
            continue
        if _is_empty(sec.body):
            report.add(WARN, "DOC004", f"'{sec.title}' section is empty.", path="README.md", line=sec.line,
                       hint="Write the content or state N/A with a reason.")
    for keywords, name in RECOMMENDED_SECTIONS:
        if find_section(sections, keywords) is None:
            report.add(WARN, "DOC005", f"README has no '{name}' section.", path="README.md")
    if not any(s.level == 1 for s in sections):
        report.add(WARN, "DOC006", "README has no top-level title (# Project Name).", path="README.md")
    return text, sections


def _env_vars_in(project: Path, listing: FileListing) -> dict[str, str]:
    found: dict[str, str] = {}
    exts = {".py", ".go", ".rs"} | JS_EXT
    for f in listing.files:
        if f.suffix not in exts:
            continue
        r = rel(f, project)
        if f.name.startswith("test_") or f.name.endswith(("_test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js")) \
                or "tests" in Path(r).parts or "__tests__" in Path(r).parts:
            continue  # variables read by tests (or fixtures inside them) are not runtime configuration
        text = read_text(f)
        if text is None:
            continue
        for pat in ENV_PATTERNS:
            for m in pat.finditer(text):
                found.setdefault(m.group(1), rel(f, project))
    return found


def check_env(project: Path, listing: FileListing, readme: str, report: Report) -> None:
    used = {k: v for k, v in _env_vars_in(project, listing).items() if k not in COMMON_ENV}
    example = read_text(project / ".env.example")
    example_keys: set[str] = set()
    if example is not None:
        for line in example.splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if m:
                example_keys.add(m.group(1))
    for var, where in sorted(used.items()):
        if example is not None and var not in example_keys:
            report.add(WARN, "ENV001", f"{var} is read in code but missing from .env.example.",
                       path=where, hint="Add it with a placeholder value.")
        if readme and var not in readme:
            report.add(WARN, "ENV002", f"{var} is read in code but not documented in the README.",
                       path=where, hint="Add it to the Configuration table.")
    for var in sorted(example_keys - set(used) - COMMON_ENV):
        if readme and var not in readme:
            report.add(WARN, "ENV003", f"{var} is in .env.example but not documented in the README.",
                       path=".env.example")


def _local_modules(project: Path, listing: FileListing) -> set[str]:
    names: set[str] = set()
    for f in listing.files:
        if f.suffix == ".py":
            names.add(f.stem)
        names.update(Path(rel(f, project)).parts[:-1])
    return names


def check_python_deps(project: Path, listing: FileListing, report: Report) -> None:
    manifest = ""
    if not any((project / n).exists() for n in ("requirements.txt", "pyproject.toml")):
        return  # FIL002 already reports a missing manifest
    for name in ("requirements.txt", "pyproject.toml"):
        manifest += (read_text(project / name) or "") + "\n"
    manifest = manifest.lower().replace("_", "-")
    local = _local_modules(project, listing)
    seen: set[str] = set()
    for f in listing.files:
        if f.suffix != ".py":
            continue
        text = read_text(f)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            report.add(WARN, "DEP002", f"Syntax error, could not check imports: {exc.msg}",
                       path=rel(f, project), line=exc.lineno)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for mod in mods:
                top = mod.split(".")[0]
                if top in sys.stdlib_module_names or top in local or top in SKIP_IMPORTS or top in seen:
                    continue
                dist = IMPORT_ALIASES.get(top, top).lower().replace("_", "-")
                if not re.search(rf"(?<![a-z0-9-]){re.escape(dist)}(?![a-z0-9])", manifest):
                    seen.add(top)
                    report.add(WARN, "DEP001", f"'{top}' is imported but not declared in the dependency manifest.",
                               path=rel(f, project), line=node.lineno,
                               hint="Add it to requirements.txt / pyproject.toml.")


def check_run_commands(project: Path, sections: list[Section], report: Report) -> None:
    pkg_scripts: set[str] | None = None
    pkg = project / "package.json"
    if pkg.exists():
        import json
        try:
            pkg_scripts = set((json.loads(read_text(pkg) or "{}").get("scripts") or {}).keys())
        except ValueError:
            report.add(ERROR, "RUN003", "package.json is not valid JSON.", path="package.json")
            pkg_scripts = set()

    def problem(code: str, msg: str, sec: Section, hint: str | None = None) -> None:
        report.add(ERROR, code, msg, path="README.md", line=sec.line, hint=hint)

    def check_target(target: str, cmd: str, sec: Section) -> None:
        if target.startswith("-") or any(c in target for c in "<>$*") or "..." in target:
            return
        if not (project / target).exists():
            problem("RUN001", f"README runs `{cmd}` but '{target}' does not exist in the project.", sec,
                    "Fix the command or the file name.")

    found_any = False
    for keywords, is_run in (((("how to run", "usage", "running")), True), (("how to test", "testing", "tests"), False)):
        sec = find_section(sections, keywords)
        if sec is None:
            continue
        for block in code_blocks(sec.body):
            for raw in block.splitlines():
                line = raw.strip().lstrip("$").strip()
                if not line or line.startswith("#"):
                    continue
                for seg in re.split(r"\s*(?:&&|;)\s*", line):
                    try:
                        toks = shlex.split(seg)
                    except ValueError:
                        continue
                    if not toks:
                        continue
                    prog, args = toks[0], toks[1:]
                    if prog in {"python", "python3", "py"} and args:
                        found_any = found_any or is_run
                        if args[0] == "-m" and len(args) > 1:
                            mod = args[1].replace(".", "/")
                            if args[1] not in {"pytest", "pip", "venv", "unittest", "http.server"} and not (
                                (project / f"{mod}.py").exists() or (project / mod).is_dir()
                            ):
                                problem("RUN001", f"README runs `{seg}` but module '{args[1]}' was not found.", sec)
                        elif not args[0].startswith("-"):
                            check_target(args[0], seg, sec)
                    elif prog in {"node", "tsx", "ts-node", "bun"} and args:
                        found_any = found_any or is_run
                        target = next((a for a in args if not a.startswith("-")), None)
                        if target:
                            check_target(target, seg, sec)
                    elif prog == "streamlit" and len(args) > 1 and args[0] == "run":
                        found_any = found_any or is_run
                        check_target(args[1], seg, sec)
                    elif prog in {"npm", "pnpm", "yarn"} and args:
                        found_any = found_any or is_run
                        script = args[1] if args[0] == "run" and len(args) > 1 else args[0]
                        if script in {"install", "i", "ci", "add"}:
                            if pkg_scripts is None:
                                problem("RUN002", f"README uses `{seg}` but there is no package.json.", sec)
                            continue
                        if pkg_scripts is None:
                            problem("RUN002", f"README uses `{seg}` but there is no package.json.", sec)
                        elif script not in pkg_scripts:
                            problem("RUN002", f"README uses `{seg}` but package.json has no '{script}' script.", sec)
                    elif prog == "pytest":
                        has_tests = any(
                            p.name.startswith("test_") or p.name.endswith("_test.py")
                            for p in project.rglob("*.py") if not (set(p.parts) & SKIP_DIRS)
                        )
                        if not has_tests:
                            report.add(WARN, "TST001", "README documents `pytest` but no test files were found.",
                                       path="README.md", line=sec.line)
    if not found_any and find_section(sections, ("how to run", "usage", "running")) is not None:
        report.add(WARN, "RUN004", "No runnable command detected in the 'How to Run' section.", path="README.md",
                   hint="Give the exact command(s) a reviewer should run.")


def check_scope(project: Path, category: str | None, base: str | None, report: Report) -> None:
    try:
        top = Path(git(["rev-parse", "--show-toplevel"], project).strip()).resolve()
    except GitError:
        report.add(INFO, "SCP000", "Not inside a git repository; PR scope check skipped.")
        return
    project_rel = project.resolve().relative_to(top).as_posix()
    candidates = [base] if base else ["upstream/main", "origin/main", "main"]
    chosen = None
    for ref in candidates:
        try:
            git(["rev-parse", "--verify", "--quiet", ref], top)
            chosen = ref
            break
        except GitError:
            continue
    if chosen is None:
        report.add(INFO, "SCP000", f"No base ref found (tried {', '.join(candidates)}); PR scope check skipped.",
                   hint="Pass --base upstream/main.")
        return
    changed: set[str] = set()
    try:
        out = git(["diff", "--name-only", f"{chosen}...HEAD"], top)
    except GitError:
        out = git(["diff", "--name-only", chosen, "HEAD"], top)
    changed.update(l for l in out.splitlines() if l)
    for line in git(["status", "--porcelain", "-uall"], top).splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ")[-1]
        changed.add(path.strip('"'))
    allowed_index = f"{category}/README.md" if category else None
    outside = sorted(
        p for p in changed
        if not p.startswith(project_rel + "/") and p != allowed_index
    )
    if outside:
        shown = ", ".join(outside[:5]) + (f" … (+{len(outside) - 5} more)" if len(outside) > 5 else "")
        report.add(ERROR, "SCP001",
                   f"{len(outside)} changed file(s) are outside {project_rel}/: {shown}",
                   hint="A PR may only touch your project folder plus one row in the category README index.")
    if project_rel and not any(p.startswith(project_rel + "/") for p in changed):
        report.add(INFO, "SCP002", f"No changes under {project_rel}/ relative to {chosen}.")


# --------------------------------------------------------------------------- entry point


def lint_project(path: str | Path, base: str | None = None) -> tuple[Report, dict]:
    """Run all deterministic checks. Returns (report, context for the optional LLM pass)."""
    project = Path(path).resolve()
    report = Report(project=str(path))
    if not project.is_dir():
        report.add(ERROR, "LOC000", f"'{path}' is not a directory.")
        return report, {}
    category = check_location(project, report)
    listing = list_files(project)
    check_required_files(project, listing, report)
    check_forbidden_files(project, listing, report)
    check_gitignore(project, report)
    tainted = check_secrets(project, listing, report)
    readme, sections = check_readme(project, report)
    check_env(project, listing, readme, report)
    check_python_deps(project, listing, report)
    check_run_commands(project, sections, report)
    check_scope(project, category, base, report)
    order = {ERROR: 0, WARN: 1, INFO: 2}
    report.findings.sort(key=lambda f: (order[f.severity], f.code, f.path or "", f.line or 0))
    ctx = {"project": project, "listing": listing, "readme": readme, "tainted": tainted}
    return report, ctx

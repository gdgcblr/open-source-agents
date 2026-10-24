"""Offline diagnosis: deterministic rules for the failures newcomers hit most often."""

from __future__ import annotations

import ast
import configparser
import difflib
import re
import shlex
import sys
from pathlib import Path
from typing import Optional

from .models import Diagnosis, Edit, Evidence, Plan, RunResult, StepResult
from .project import IGNORED_DIRS, find_readme, list_files, read_text
from .readme import (
    DIRECTIVE_RE, HEADING_RE, IGNORED_LANGS, KNOWN_COMMANDS, command_word, documented_output,
    extract_plan, locate_line, parse_code_blocks, program_of,
)

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

# import name -> name on PyPI, for the cases where they differ
PACKAGE_MAP: dict[str, str] = {
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "jwt": "PyJWT",
    "jose": "python-jose",
    "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodomex",
    "serial": "pyserial",
    "usb": "pyusb",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "fitz": "PyMuPDF",
    "pymupdf": "PyMuPDF",
    "git": "GitPython",
    "github": "PyGithub",
    "gitlab": "python-gitlab",
    "telegram": "python-telegram-bot",
    "discord": "discord.py",
    "attr": "attrs",
    "OpenSSL": "pyOpenSSL",
    "magic": "python-magic",
    "dns": "dnspython",
    "multipart": "python-multipart",
    "slugify": "python-slugify",
    "nacl": "PyNaCl",
    "zmq": "pyzmq",
    "socketio": "python-socketio",
    "engineio": "python-engineio",
    "websocket": "websocket-client",
    "psycopg2": "psycopg2-binary",
    "MySQLdb": "mysqlclient",
    "Bio": "biopython",
    "kafka": "kafka-python",
    "gi": "PyGObject",
    "win32api": "pywin32",
    "win32con": "pywin32",
    "Levenshtein": "python-Levenshtein",
    "speech_recognition": "SpeechRecognition",
    "pkg_resources": "setuptools",
    "faiss": "faiss-cpu",
    "sentence_transformers": "sentence-transformers",
    "llama_index": "llama-index",
    "tavily": "tavily-python",
    "duckduckgo_search": "duckduckgo-search",
    "pydantic_settings": "pydantic-settings",
    "readability": "readability-lxml",
    "newspaper": "newspaper3k",
    "markdown": "Markdown",
    "jinja2": "Jinja2",
    "googleapiclient": "google-api-python-client",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "vertexai": "google-cloud-aiplatform",
    "google.genai": "google-genai",
    "google.generativeai": "google-generativeai",
    "google.adk": "google-adk",
    "google.auth": "google-auth",
    "google.oauth2": "google-auth",
    "google.protobuf": "protobuf",
    "google.api_core": "google-api-core",
    "google.cloud.aiplatform": "google-cloud-aiplatform",
    "huggingface_hub": "huggingface-hub",
    "mcp": "mcp",
    "fastmcp": "fastmcp",
}

# console commands that come from a pip package
PIP_CLIS = {
    "streamlit": "streamlit", "uvicorn": "uvicorn", "pytest": "pytest", "flask": "Flask",
    "gunicorn": "gunicorn", "adk": "google-adk", "black": "black", "ruff": "ruff",
    "mypy": "mypy", "jupyter": "jupyter", "gradio": "gradio", "chainlit": "chainlit",
    "mkdocs": "mkdocs", "alembic": "alembic", "celery": "celery", "fastapi": "fastapi[standard]",
    "huggingface-cli": "huggingface-hub", "pre-commit": "pre-commit", "dotenv": "python-dotenv[cli]",
}
PACKAGE_MANAGERS = {"uv", "poetry", "pipenv", "pdm", "hatch", "pipx", "tox", "nox"}
NODE_TOOLS = {"npm", "npx", "node", "yarn", "pnpm"}
INSTALL_RE = re.compile(
    r"\b(?:pip3?|uv\s+pip)\s+install\b|\buv\s+sync\b|\bpoetry\s+install\b|\bpipenv\s+install\b"
    r"|\bpdm\s+install\b|\bconda\s+env\s+(?:create|update)\b|\bpython3?\s+-m\s+pip\s+install\b"
)
CREDENTIAL_PATTERNS = [
    r"api[ _-]?key not valid", r"invalid[ _-]api[ _-]?key", r"incorrect api key",
    r"api_key client option must be set", r"missing key inputs argument", r"no api[ _-]?key",
    r"missing api[ _-]?key",
    r"api[ _-]?key (?:is )?(?:missing|required|not (?:set|found|provided))", r"api key expired",
    r"please (?:pass|provide|set) (?:a )?valid api key", r"\bunauthenticated\b",
    r"permission_denied", r"defaultcredentialserror", r"could not automatically determine credentials",
    r"\b401\b[^\n]*unauthori[sz]ed", r"unauthori[sz]ed[^\n]*\b401\b", r"\b403\b[^\n]*forbidden",
    r"authenticationerror", r"authentication failed", r"invalid_api_key", r"invalid x-api-key",
]
SECRET_VAR = r"[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?)[A-Z0-9_]*"
# (where the failing output points, env names that belong to that service, usual names)
SERVICES = [
    (r"api\.github\.com|github", r"GITHUB|^GH_", ["GITHUB_TOKEN"]),
    (r"generativelanguage|api key not valid|google\.genai|google\.generativeai|gemini",
     r"GEMINI|GOOGLE", ["GEMINI_API_KEY", "GOOGLE_API_KEY"]),
    (r"openai", r"OPENAI", ["OPENAI_API_KEY"]),
    (r"anthropic", r"ANTHROPIC|CLAUDE", ["ANTHROPIC_API_KEY"]),
]
TEST_DIRS = {"tests", "test", "testing", "fixtures", "testdata", "evals", "eval"}
SAMPLE_DIRS = ("examples", "example", "samples", "sample", "data", "tests/fixtures", "test/fixtures", "fixtures")
# a FileNotFoundError raised while starting a program, not while opening a data file
SUBPROCESS_MARKERS = re.compile(r"_execute_child|subprocess\.py|os\.exec|\bPopen\b|shutil\.which")
# tools that need the host itself (a container runtime, a cluster, an init system), which a
# throwaway sandbox cannot give a project
HOST_TOOLS = {"docker", "docker-compose", "podman", "kubectl", "minikube", "kind", "k3d", "systemctl", "service"}
TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)")
TOOL_ALIASES = {
    "node": ("node", "node.js", "nodejs"), "npm": ("npm", "node", "node.js", "nodejs"),
    "npx": ("npx", "npm", "node", "node.js", "nodejs"), "java": ("java", "jdk", "jre"),
    "docker": ("docker",), "git": ("git",),
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _stdlib() -> set[str]:
    names = set(getattr(sys, "stdlib_module_names", ()))
    return names | {"__future__", "__main__"}


STDLIB = _stdlib()


def _is_test_path(rel: str) -> bool:
    parts = Path(rel).parts
    name = parts[-1] if parts else ""
    return (any(part in TEST_DIRS for part in parts[:-1]) or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def _py_files(project_dir: Path):
    for p in sorted(project_dir.rglob("*.py")):
        rel = p.relative_to(project_dir)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        yield p, rel.as_posix()


def _local_modules(project_dir: Path) -> set[str]:
    names = set()
    for p, _ in _py_files(project_dir):
        names.add(p.stem)
        for parent in p.relative_to(project_dir).parents:
            if parent.name:
                names.add(parent.name)
    return names


def _guarded_lines(tree: ast.AST) -> set[int]:
    """Lines of imports wrapped in try/except ImportError, which are optional on purpose."""
    lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches = False
        for h in node.handlers:
            names = []
            if h.type is None:
                catches = True
            elif isinstance(h.type, ast.Name):
                names = [h.type.id]
            elif isinstance(h.type, ast.Tuple):
                names = [e.id for e in h.type.elts if isinstance(e, ast.Name)]
            if any(n in ("ImportError", "ModuleNotFoundError", "Exception") for n in names):
                catches = True
        if catches:
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        lines.add(sub.lineno)
    return lines


def _import_statements(project_dir: Path) -> list[tuple[str, str, int]]:
    """(dotted name, file, line) for every absolute import in the project."""
    out = []
    for path, rel in _py_files(project_dir):
        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        guarded = _guarded_lines(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and node.lineno not in guarded:
                for alias in node.names:
                    out.append((alias.name, rel, node.lineno))
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.lineno not in guarded:
                for alias in node.names:
                    out.append((f"{node.module}.{alias.name}", rel, node.lineno))
    return out


def scan_imports(project_dir: Path) -> dict[str, list[tuple[str, int]]]:
    """Third-party top-level modules the code imports, with where they are imported."""
    local = _local_modules(project_dir)
    found: dict[str, list[tuple[str, int]]] = {}
    for dotted, rel, line in _import_statements(project_dir):
        top = dotted.split(".")[0]
        if top in STDLIB or top in local:
            continue
        found.setdefault(top, []).append((rel, line))
    return found


def module_to_package(module: str, project_dir: Optional[Path] = None) -> str:
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        key = ".".join(parts[:i])
        if key in PACKAGE_MAP:
            return PACKAGE_MAP[key]
    top = parts[0]
    if top == "google":
        if len(parts) >= 3 and parts[1] == "cloud":
            return "google-cloud-" + parts[2].replace("_", "-")
        if len(parts) == 1 and project_dir is not None:
            # "No module named 'google'": look at what the code actually pulls from google.*
            for dotted, _, _ in _import_statements(project_dir):
                if dotted.startswith("google.") and dotted.count(".") >= 1:
                    guess = module_to_package(dotted)
                    if guess and normalize(guess) != "google":
                        return guess
        if len(parts) >= 2:
            return "google-" + parts[1].replace("_", "-")
        return "google-genai"
    if top == "azure" and len(parts) >= 2:
        return "azure-" + "-".join(p.replace("_", "-") for p in parts[1:3] if p.islower())
    return top.replace("_", "-")


def _req_name(line: str) -> Optional[str]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    egg = re.search(r"#egg=([A-Za-z0-9._-]+)", line)
    if egg:
        return egg.group(1)
    line = re.split(r"\s+#", line, 1)[0].strip()
    if line.startswith("-"):
        return None
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
    return m.group(1) if m else None


def _requirements_files(project_dir: Path) -> list[Path]:
    files = sorted(project_dir.glob("requirements*.txt"))
    req_dir = project_dir / "requirements"
    if req_dir.is_dir():
        files += sorted(req_dir.glob("*.txt"))
    return files


def _read_requirements(path: Path, seen: set[Path]) -> set[str]:
    if path in seen or not path.is_file():
        return set()
    seen.add(path)
    names = set()
    for raw in (read_text(path) or "").splitlines():
        inc = re.match(r"^\s*(?:-r|--requirement)\s*=?\s*(\S+)", raw)
        if inc:
            names |= _read_requirements((path.parent / inc.group(1)).resolve(), seen)
            continue
        name = _req_name(raw)
        if name:
            names.add(normalize(name))
    return names


def declared_packages(project_dir: Path) -> set[str]:
    names: set[str] = set()
    seen: set[Path] = set()
    for f in _requirements_files(project_dir):
        names |= _read_requirements(f.resolve(), seen)

    pyproject = read_text(project_dir / "pyproject.toml")
    if pyproject:
        data = {}
        if tomllib is not None:
            try:
                data = tomllib.loads(pyproject)
            except Exception:
                data = {}
        project = data.get("project", {})
        reqs = list(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            reqs += list(group)
        for group in data.get("dependency-groups", {}).values():
            reqs += [r for r in group if isinstance(r, str)]
        poetry = data.get("tool", {}).get("poetry", {})
        reqs += [k for k in poetry.get("dependencies", {}) if k.lower() != "python"]
        for group in poetry.get("group", {}).values():
            reqs += list(group.get("dependencies", {}))
        if not data:
            reqs += re.findall(r"^\s*\"([A-Za-z0-9][A-Za-z0-9._-]*)", pyproject, re.M)
        for r in reqs:
            n = _req_name(r)
            if n:
                names.add(normalize(n))

    setup_py = read_text(project_dir / "setup.py")
    if setup_py:
        m = re.search(r"install_requires\s*=\s*\[(.*?)\]", setup_py, re.S)
        if m:
            for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
                n = _req_name(s)
                if n:
                    names.add(normalize(n))
    setup_cfg = read_text(project_dir / "setup.cfg")
    if setup_cfg:
        cfg = configparser.ConfigParser()
        try:
            cfg.read_string(setup_cfg)
            for s in cfg.get("options", "install_requires", fallback="").splitlines():
                n = _req_name(s)
                if n:
                    names.add(normalize(n))
        except configparser.Error:
            pass
    pipfile = read_text(project_dir / "Pipfile")
    if pipfile and tomllib is not None:
        try:
            data = tomllib.loads(pipfile)
            for section in ("packages", "dev-packages"):
                names |= {normalize(k) for k in data.get(section, {})}
        except Exception:
            pass
    return names


def _has_manifest(project_dir: Path) -> bool:
    return bool(_requirements_files(project_dir)) or any(
        (project_dir / n).is_file() for n in ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile")
    )


def _is_declared(module: str, project_dir: Path, declared: set[str]) -> bool:
    pkg = normalize(module_to_package(module, project_dir).split("[")[0])
    return pkg in declared


def _env_reads(project_dir: Path, include_tests: bool = False) -> list[tuple[str, str, int]]:
    """Secret-looking environment variables the code reads: (name, file, line).

    Tests, fixtures and evals are left out by default: a key only a test reads is not something
    a newcomer needs.
    """
    pattern = re.compile(
        r"(?:os\.environ\.get|os\.getenv|os\.environ\[|environ\.get|getenv)\s*\(?\s*['\"](" + SECRET_VAR + r")['\"]"
    )
    out = []
    for path, rel in _py_files(project_dir):
        if not include_tests and _is_test_path(rel):
            continue
        for i, line in enumerate((read_text(path) or "").splitlines(), 1):
            for m in pattern.finditer(line):
                out.append((m.group(1), rel, i))
    return out


def static_hints(project_dir: Path) -> list[str]:
    """Cheap checks that do not need to run anything."""
    hints: list[str] = []
    readme = find_readme(project_dir)
    if readme is None:
        hints.append("No README found, so a newcomer has no setup instructions to follow.")
    imports = scan_imports(project_dir)
    declared = declared_packages(project_dir)
    if imports and not _has_manifest(project_dir):
        hints.append(
            "No dependency manifest (requirements.txt or pyproject.toml), but the code imports "
            + ", ".join(sorted(imports)[:6]) + "."
        )
    else:
        statements = {}
        for dotted, rel, line in _import_statements(project_dir):
            top = dotted.split(".")[0]
            if top in imports and top not in statements:
                statements[top] = (dotted, rel, line)
        for top in sorted(imports):
            dotted, rel, line = statements[top]
            if not _is_declared(dotted, project_dir, declared) and normalize(top) not in declared:
                pkg = module_to_package(dotted, project_dir)
                hints.append(f"{rel}:{line} imports {top}, but no manifest declares {pkg}")
            if len(hints) >= 10:
                break
    documented = (read_text(project_dir / ".env.example") or "") + (read_text(readme) if readme else "")
    reported = set()
    for name, rel, line in _env_reads(project_dir):
        if name not in documented and name not in reported:
            hints.append(f"{rel}:{line} reads {name}, but neither the README nor .env.example mentions it")
            reported.add(name)
    if (project_dir / ".env").is_file():
        hints.append("A .env file is present in the project folder; make sure it is not committed.")
    if readme is not None:
        hints += _placeholder_hints(project_dir)
    return hints


def _sample_file(project_dir: Path, suffix: str) -> Optional[str]:
    for folder in SAMPLE_DIRS:
        base = project_dir / folder
        if base.is_dir():
            hits = sorted(p.relative_to(project_dir).as_posix() for p in base.rglob(f"*{suffix}") if p.is_file())
            if hits:
                return hits[0]
    return None


def _placeholder_hints(project_dir: Path) -> list[str]:
    """Run commands the planner skipped because they need the reader's own input."""
    plan = extract_plan(project_dir)
    rel = plan.readme_path or "README"
    hints: list[str] = []
    for k in plan.skipped:
        m = re.match(r"needs your own input \(placeholder `([^`]+)`\)", k.reason)
        if not m:
            continue
        placeholder = m.group(1)
        suffix = Path(placeholder.split("=", 1)[-1]).suffix
        suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix) else ""
        where = f"{rel}:{k.line}" if k.line else rel
        cmd = " ".join(k.command.split())
        cmd = cmd if len(cmd) <= 80 else cmd[:77] + "..."
        sample = _sample_file(project_dir, suffix) if suffix else None
        if sample:
            hints.append(f"{where} runs `{cmd}` with a placeholder ({placeholder}). {sample} is in the project, "
                         "so the README could use it as an example that runs as written.")
        elif suffix:
            hints.append(f"{where} runs `{cmd}` with a placeholder ({placeholder}), and there is no sample "
                         f"{suffix} file in the project to point it at.")
        else:
            hints.append(f"{where} runs `{cmd}` with a placeholder ({placeholder}), so a newcomer has to "
                         "invent their own input.")
        if len(hints) >= 3:
            break
    if hints and not any(s.kind in ("run", "test") for s in plan.steps):
        hints.append("The README has no runnable example: every run command needs input the reader has to supply.")
    return hints


NETWORK_PATTERNS = [
    r"Read timed out", r"Max retries exceeded", r"Temporary failure in name resolution",
    r"Could not resolve host", r"Connection reset by peer", r"Network is unreachable",
    r"Name or service not known", r"No route to host", r"ConnectTimeoutError",
    r"Failed to establish a new connection", r"TLS handshake timeout",
]


def is_network_flake(output: str) -> bool:
    """True when a step died because the sandbox could not reach the network, not the project."""
    tail = "\n".join(output.strip().splitlines()[-40:])
    return any(re.search(p, tail) for p in NETWORK_PATTERNS)


def detect_credentials(output: str, project_dir: Path) -> Optional[list[str]]:
    """Env var names when a failure looks like missing or rejected credentials, else None.

    An empty list means it is clearly a credentials problem but the variable is unknown.
    """
    names: list[str] = []
    for m in re.finditer(r"KeyError: ['\"](" + SECRET_VAR + r")['\"]", output):
        names.append(m.group(1))
    for m in re.finditer(
        r"\b(" + SECRET_VAR + r")\b[^\n]{0,60}?\b(?:is not set|not set|missing|is required|required|"
        r"not found|undefined|must be set|is empty|not configured)",
        output,
        re.I,
    ):
        if m.group(1).isupper():
            names.append(m.group(1))
    for m in re.finditer(
        r"\b(?:missing|set|provide|export|no)\b[^\n]{0,40}?\b(" + SECRET_VAR + r")\b", output, re.I
    ):
        if m.group(1).isupper():
            names.append(m.group(1))
    generic = any(re.search(p, output, re.I) for p in CREDENTIAL_PATTERNS)
    if not names and not generic:
        return None
    from .readme import _secret_envs  # noqa: local import to avoid a cycle at import time

    readme = find_readme(project_dir)
    known = _secret_envs(project_dir, read_text(readme) if readme else "")
    known += [n for n, _, _ in _env_reads(project_dir)]
    by_service, canonical = _rank_by_service(output, known)
    if names:
        # the error names the variable; add only the keys of the service that failed
        ordered = names + by_service
    else:
        # the error does not say which variable: the failing service first, then the rest of
        # what the project documents, in .env.example order
        ordered = by_service + known
        if not ordered:
            ordered = canonical
    unique = []
    for n in ordered:
        if n not in unique:
            unique.append(n)
    return unique


def _rank_by_service(output: str, known: list[str]) -> tuple[list[str], list[str]]:
    """Known env names that belong to the service the output points at, nearest mention first.

    Also returns the usual names of the most likely service, for projects that document none.
    """
    hits = []
    for pattern, names_re, usual in SERVICES:
        found = list(re.finditer(pattern, output, re.I))
        if found:
            hits.append((found[-1].start(), names_re, usual))
    hits.sort(key=lambda h: -h[0])
    ranked: list[str] = []
    for _, names_re, usual in hits:
        own = [n for n in known if re.search(names_re, n) and n not in ranked]
        own.sort(key=lambda n: usual.index(n) if n in usual else len(usual))
        ranked += own
    return ranked, (hits[0][2] if hits else [])


# README editing helpers


def _readme(project_dir: Path, plan: Plan) -> tuple[Optional[str], Optional[str]]:
    path = project_dir / plan.readme_path if plan.readme_path else find_readme(project_dir)
    if path is None or not path.is_file():
        return None, None
    return path.relative_to(project_dir).as_posix(), read_text(path)


def _line_edits(rel: str, text: str, replacements: dict[int, list[str]]) -> list[Edit]:
    """Turn {line_number: new lines} into edits whose 'old' text is unique in the file.

    Context lines are added around a target until it is unique, and nearby targets are merged
    so the edits never overlap.
    """
    lines = text.split("\n")
    ranges = [[n - 1, n - 1] for n in sorted(replacements)]

    def old_text(r):
        block = "\n".join(lines[r[0]:r[1] + 1])
        return block + "\n" if r[1] < len(lines) - 1 else block

    while True:
        ranges.sort()
        merged: list[list[int]] = []
        for r in ranges:
            if merged and r[0] <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], r[1])
            else:
                merged.append(list(r))
        grew = False
        for r in merged:
            while text.count(old_text(r)) > 1:
                if r[0] > 0:
                    r[0] -= 1
                elif r[1] < len(lines) - 1:
                    r[1] += 1
                else:
                    break
                grew = True
        ranges = merged
        if not grew:
            break

    edits = []
    for r in ranges:
        new_lines: list[str] = []
        for idx in range(r[0], r[1] + 1):
            new_lines.extend(replacements.get(idx + 1, [lines[idx]]))
        trailing = r[1] < len(lines) - 1
        new = "\n".join(new_lines) + ("\n" if trailing and new_lines else "")
        edits.append(Edit(path=rel, old=old_text(r), new=new))
    return edits


def _prefix(line: str) -> str:
    m = re.match(r"^(\s*(?:\$\s+)?)", line)
    return m.group(1) if m else ""


def _insert_before(rel: str, text: str, line_no: int, command: str) -> list[Edit]:
    lines = text.split("\n")
    target = lines[line_no - 1]
    return _line_edits(rel, text, {line_no: [_prefix(target) + command, target]})


def _step_line(step_result: StepResult, readme_text: Optional[str]) -> Optional[int]:
    if step_result.step.line:
        return step_result.step.line
    if readme_text and not step_result.step.provided_by_firstrun:
        return locate_line(readme_text, step_result.step.command)
    return None


def _code_lines(readme_text: str) -> list[tuple[int, str]]:
    """(line number, original text) of README lines that are shell commands."""
    out = []
    raw = readme_text.split("\n")
    for b in parse_code_blocks(readme_text):
        if b["lang"] in IGNORED_LANGS:
            continue
        for ln, text in b["lines"]:
            s = re.sub(r"^\s*(?:\$\s+)?", "", text)
            if command_word(s) in KNOWN_COMMANDS or s.startswith("./"):
                out.append((ln, raw[ln - 1]))
    return out


def _tail(output: str, n: int = 40) -> str:
    return "\n".join(output.splitlines()[-n:])


def _last(pattern: str, output: str, flags: int = 0) -> Optional[re.Match]:
    matches = list(re.finditer(pattern, output, flags))
    return matches[-1] if matches else None


def _install_command(project_dir: Path) -> str:
    if (project_dir / "requirements.txt").is_file():
        return "pip install -r requirements.txt"
    reqs = _requirements_files(project_dir)
    if reqs:
        return f"pip install -r {reqs[0].relative_to(project_dir).as_posix()}"
    return "pip install ."


def _requirements_target(project_dir: Path, results: list[StepResult]) -> Optional[str]:
    """The requirements file the newcomer actually installed from, if any."""
    for r in results:
        m = re.search(r"(?:-r|--requirement)\s*=?\s*(\S+\.txt)", r.step.command)
        if m and (project_dir / m.group(1)).is_file():
            return m.group(1)
    if (project_dir / "requirements.txt").is_file():
        return "requirements.txt"
    reqs = _requirements_files(project_dir)
    return reqs[0].relative_to(project_dir).as_posix() if reqs else None


def _dependency_edit(project_dir: Path, pkg: str, results: list[StepResult]) -> tuple[list[Edit], str]:
    target = _requirements_target(project_dir, results)
    if target:
        return [Edit(path=target, old="", new=pkg + "\n")], target
    pyproject = read_text(project_dir / "pyproject.toml")
    if pyproject:
        m = re.search(r"^dependencies\s*=\s*\[", pyproject, re.M)
        if m and pyproject.count(m.group(0)) == 1:
            old = m.group(0)
            return [Edit(path="pyproject.toml", old=old, new=f'{old}\n    "{pkg}",')], "pyproject.toml"
        return [], "pyproject.toml"
    return [Edit(path="requirements.txt", old="", new=pkg + "\n")], "requirements.txt"


# Individual rules. Each returns a Diagnosis or None.


def _rule_missing_module(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(r"No module named ['\"]?([\w.]+)['\"]?", failed.output)
    if not m:
        return None
    module = m.group(1)
    top = module.split(".")[0]
    local = _local_modules(project_dir)
    if top in local and top not in STDLIB:
        where = next((rel for _, rel in _py_files(project_dir) if Path(rel).stem == top or f"/{top}/" in f"/{rel}"), top)
        return Diagnosis(
            category="wrong_command",
            summary=f"`{top}` is a module inside the project ({where}), so the command is probably run from the wrong folder.",
            explanation=(
                f"Python could not import {module}, but {where} exists in the project. The documented "
                "command likely needs a different working directory, `python -m`, or a PYTHONPATH change."
            ),
            evidence=[Evidence(file=where, line=None, note=f"local module {top}")],
            confidence="low",
        )
    if top in STDLIB:
        return Diagnosis(
            category="platform_issue",
            summary=f"`{module}` is part of the standard library but is missing from this Python build.",
            explanation="The interpreter in the sandbox lacks this module (for example tkinter on slim images).",
            confidence="low",
        )
    pkg = module_to_package(module, project_dir)
    declared = declared_packages(project_dir)
    evidence = []
    for dotted, rel, line in _import_statements(project_dir):
        if dotted.split(".")[0] == top:
            evidence.append(Evidence(file=rel, line=line, note=f"imports {top}"))
            if len(evidence) >= 3:
                break
    importer = f"{evidence[0].file}" if evidence else "The code"
    earlier = [r for r in run.results if r is not failed and r.status in ("passed", "alive")]
    installed = any(INSTALL_RE.search(r.step.command) for r in earlier)

    if normalize(pkg) in declared:
        if not installed and readme_rel and readme_text:
            line_no = _step_line(failed, readme_text)
            cmd = _install_command(project_dir)
            edits = _insert_before(readme_rel, readme_text, line_no, cmd) if line_no else []
            return Diagnosis(
                category="undocumented_step",
                summary=f"{pkg} is declared, but the README never tells you to install the dependencies.",
                explanation=(
                    f"The dependency is listed in the manifest, but no install command runs before "
                    f"`{failed.step.command}`. Adding `{cmd}` to the README fixes the path for newcomers."
                ),
                evidence=evidence + [Evidence(file=readme_rel, line=line_no, note="command that needs the dependencies")],
                edits=edits,
                confidence="high" if edits else "medium",
            )
        return Diagnosis(
            category="unknown",
            summary=f"{pkg} is declared and an install step ran, yet `{module}` still cannot be imported.",
            explanation=(
                "The package may have been installed into a different interpreter (for example the "
                "virtualenv is activated after the install), or the import comes from an extra."
            ),
            evidence=evidence,
            confidence="low",
        )
    if normalize(top) in declared and normalize(top) != normalize(pkg):
        target = _requirements_target(project_dir, run.results)
        text = read_text(project_dir / target) if target else None
        for ln, raw in enumerate((text or "").split("\n"), 1):
            name = _req_name(raw)
            if name and normalize(name) == normalize(top):
                return Diagnosis(
                    category="missing_dependency",
                    summary=f"{target} lists `{name}`, but `import {top}` comes from {pkg}.",
                    explanation=f"The PyPI package `{name}` does not provide the `{top}` module the code imports.",
                    evidence=evidence + [Evidence(file=target, line=ln, note=f"declares {name}")],
                    edits=_line_edits(target, text, {ln: [raw.replace(name, pkg, 1)]}),
                    confidence="high",
                )
    edits, manifest = _dependency_edit(project_dir, pkg, run.results)
    return Diagnosis(
        category="missing_dependency",
        summary=f"{importer} imports {top}, but {manifest} does not declare {pkg}.",
        explanation=(
            f"`{failed.step.command}` failed with ModuleNotFoundError: No module named '{module}'. "
            f"The import is provided by the PyPI package {pkg}, which is missing from the dependency list, "
            "so it only works on machines where it happens to be installed already."
        ),
        evidence=evidence + [Evidence(file=manifest, line=None, note=f"does not list {pkg}")],
        edits=edits,
        confidence="high" if edits else "medium",
    )


def _rule_credentials(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    names = detect_credentials(failed.output, project_dir)
    if names is None:
        return None
    example = read_text(project_dir / ".env.example")
    documented_text = (example or "") + (readme_text or "")
    read_by_code = {n for n, _, _ in _env_reads(project_dir)}
    undocumented = [n for n in names if n in read_by_code and n not in documented_text]
    edits = []
    if undocumented:
        edits = [Edit(path=".env.example", old="", new="".join(f"{n}=your_value_here\n" for n in undocumented))]
    evidence = []
    if readme_rel and readme_text:
        for n in names:
            ln = next((i for i, l in enumerate(readme_text.splitlines(), 1) if n in l), None)
            if ln:
                evidence.append(Evidence(file=readme_rel, line=ln, note=f"documents {n}"))
    for n, rel, line in _env_reads(project_dir):
        if n in names:
            evidence.append(Evidence(file=rel, line=line, note=f"reads {n}"))
    label = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "") if names else "an API credential"
    summary = f"Blocked: credentials required ({label}). FirstRun will not invent a key."
    if undocumented:
        summary += f" {', '.join(undocumented)} is not documented anywhere."
    return Diagnosis(
        category="credentials_required",
        summary=summary,
        explanation=(
            "The run stopped at a point that needs a real credential. Supply it with --env-file "
            "(it is passed into the sandbox and never written to the report) and run FirstRun again."
        ),
        evidence=evidence,
        edits=edits,
        blocked=True,
        missing_env=names,
        confidence="high",
    )


def _node_block_edits(readme_rel: str, readme_text: str) -> list[Edit]:
    """Remove Node commands (and code blocks made only of them) from a Python project's README."""
    lines = readme_text.split("\n")
    remove: set[int] = set()
    for b in parse_code_blocks(readme_text):
        cmd_lines = [(ln, t) for ln, t in b["lines"] if t.strip() and not t.strip().startswith("#")]
        node = [ln for ln, t in cmd_lines if command_word(t.strip().lstrip("$ ")) in NODE_TOOLS]
        if not node:
            continue
        if len(node) == len(cmd_lines):
            span = set(range(b["start"], b["end"] + 1))
            above = b["start"] - 1
            while above >= 1 and not lines[above - 1].strip():
                above -= 1
            if above >= 1 and re.search(r"node|npm|typescript|javascript|yarn|pnpm", lines[above - 1], re.I):
                span |= set(range(above, b["start"]))
            remove |= span
        else:
            for ln in node:
                remove.add(ln)
                prev = ln - 1
                if prev >= 1 and lines[prev - 1].strip().startswith("#") and re.search(
                    r"node|npm|typescript|javascript|yarn|pnpm", lines[prev - 1], re.I
                ):
                    remove.add(prev)
    if not remove:
        return []
    return _line_edits(readme_rel, readme_text, {n: [] for n in sorted(remove)})


def _rule_command_not_found(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(r"(?:^|\s|:\s)([\w.+/-]+): (?:command )?not found", failed.output, re.M)
    if not m and failed.exit_code != 127:
        return None
    tool = Path(m.group(1)).name if m else command_word(failed.step.command)
    line_no = _step_line(failed, readme_text)
    readme_ev = [Evidence(file=readme_rel, line=line_no, note=f"runs {tool}")] if readme_rel else []

    if tool in NODE_TOOLS and not (project_dir / "package.json").is_file():
        edits = _node_block_edits(readme_rel, readme_text) if readme_rel and readme_text else []
        return Diagnosis(
            category="template_leftover",
            summary=f"The README tells you to run `{failed.step.command}`, but this is a Python project with no package.json.",
            explanation=(
                "These Node.js lines look like leftovers from the contribution template. They fail for "
                "every newcomer, so the fix is to remove them from the README."
            ),
            evidence=readme_ev,
            edits=edits,
            confidence="high" if edits else "medium",
        )
    if tool in PACKAGE_MANAGERS:
        cmd = f"pip install {tool}"
        edits = _insert_before(readme_rel, readme_text, line_no, cmd) if readme_rel and readme_text and line_no else []
        return Diagnosis(
            category="undocumented_step",
            summary=f"The README uses `{tool}` but never says to install it.",
            explanation=f"`{tool}` is not part of a standard Python install. Adding `{cmd}` before it makes the step work.",
            evidence=readme_ev,
            edits=edits,
            confidence="medium",
        )
    if tool in PIP_CLIS:
        pkg = PIP_CLIS[tool]
        declared = declared_packages(project_dir)
        if normalize(pkg.split("[")[0]) in declared:
            earlier = [r for r in run.results if r is not failed and r.ok]
            if not any(INSTALL_RE.search(r.step.command) for r in earlier) and readme_rel and line_no:
                cmd = _install_command(project_dir)
                return Diagnosis(
                    category="undocumented_step",
                    summary=f"`{tool}` comes from {pkg}, which is declared but never installed by the README steps.",
                    explanation=f"Add `{cmd}` before `{failed.step.command}`.",
                    evidence=readme_ev,
                    edits=_insert_before(readme_rel, readme_text, line_no, cmd),
                    confidence="high",
                )
            return None
        edits, manifest = _dependency_edit(project_dir, pkg, run.results)
        return Diagnosis(
            category="missing_dependency",
            summary=f"The README runs `{tool}`, but {manifest} does not declare {pkg}.",
            explanation=f"`{tool}` is a command installed by the {pkg} package, which is missing from the dependency list.",
            evidence=readme_ev + [Evidence(file=manifest, line=None, note=f"does not list {pkg}")],
            edits=edits,
            confidence="high" if edits else "medium",
        )
    if re.match(r"^python\d(?:\.\d+)?$", tool):
        return Diagnosis(
            category="platform_issue",
            summary=f"The README calls `{tool}`, a specific interpreter version that is not installed here.",
            explanation="Consider documenting the required Python version or using plain `python`.",
            evidence=readme_ev,
            confidence="medium",
        )
    return None


def _entry_point(project_dir: Path, wanted: str) -> Optional[str]:
    name = Path(wanted).name
    same = [rel for _, rel in _py_files(project_dir) if Path(rel).name == name]
    if same:
        return sorted(same, key=len)[0]
    mains = []
    for path, rel in _py_files(project_dir):
        text = read_text(path) or ""
        if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", text) and not rel.startswith("tests/"):
            mains.append(rel)
    if len(mains) == 1:
        return mains[0]
    close = difflib.get_close_matches(name, [Path(m).name for m in mains], n=1)
    if close:
        return next(m for m in mains if Path(m).name == close[0])
    return None


def _replace_token_edits(readme_rel: str, readme_text: str, token: str, replacement: str) -> list[Edit]:
    pattern = re.compile(r"(?<![\w/.-])" + re.escape(token) + r"(?![\w/-])")
    replacements = {}
    for ln, raw in _code_lines(readme_text):
        if pattern.search(raw):
            replacements[ln] = [pattern.sub(replacement, raw)]
    return _line_edits(readme_rel, readme_text, replacements) if replacements else []


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command.replace("\\\n", " "))
    except ValueError:
        return command.split()


def _rule_cant_open(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(r"can't open file ['\"]([^'\"]+)['\"]", failed.output)
    if not m:
        return None
    missing = m.group(1)
    tokens = _command_tokens(failed.step.command)
    token = next((t for t in tokens if Path(t).name == Path(missing).name), Path(missing).name)
    real = _entry_point(project_dir, token)
    line_no = _step_line(failed, readme_text)
    evidence = [Evidence(file=readme_rel or "README", line=line_no, note=f"runs {token}")]
    if not real or real == token:
        return Diagnosis(
            category="wrong_command",
            summary=f"The README runs `{token}`, but no such script exists in the project.",
            explanation="FirstRun could not find a single obvious entry point to point the command at.",
            evidence=evidence,
            confidence="low",
        )
    edits = _replace_token_edits(readme_rel, readme_text, token, real) if readme_rel and readme_text else []
    return Diagnosis(
        category="wrong_command",
        summary=f"The README runs `{token}`, but the script is at `{real}`.",
        explanation=(
            f"`{failed.step.command}` fails because {token} is not in the project root. "
            f"The documented command should point at {real}."
        ),
        evidence=evidence + [Evidence(file=real, line=None, note="actual entry point")],
        edits=edits,
        confidence="high" if edits else "medium",
    )


def _rule_requirements_file(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(r"Could not open requirements file: \[Errno 2\] No such file or directory: ['\"]([^'\"]+)['\"]", failed.output)
    if not m:
        return None
    wanted = m.group(1)
    line_no = _step_line(failed, readme_text)
    evidence = [Evidence(file=readme_rel or "README", line=line_no, note=f"installs from {wanted}")]
    if (project_dir / "pyproject.toml").is_file() or (project_dir / "setup.py").is_file():
        edits = []
        if readme_rel and readme_text:
            pattern = re.compile(r"(?:-r|--requirement)\s*=?\s*" + re.escape(wanted) + r"(?![\w.-])")
            replacements = {ln: [pattern.sub(".", raw)] for ln, raw in _code_lines(readme_text) if pattern.search(raw)}
            edits = _line_edits(readme_rel, readme_text, replacements) if replacements else []
        manifest = "pyproject.toml" if (project_dir / "pyproject.toml").is_file() else "setup.py"
        return Diagnosis(
            category="missing_file",
            summary=f"The README installs from {wanted}, which does not exist; dependencies live in {manifest}.",
            explanation=f"Installing the project itself (`pip install .`) reads the dependencies from {manifest}.",
            evidence=evidence + [Evidence(file=manifest, line=None, note="declares the dependencies")],
            edits=edits,
            confidence="high" if edits else "medium",
        )
    others = [p.relative_to(project_dir).as_posix() for p in project_dir.rglob("requirement*.txt")
              if not any(part in IGNORED_DIRS for part in p.relative_to(project_dir).parts)]
    if others and readme_rel and readme_text:
        real = sorted(others, key=len)[0]
        return Diagnosis(
            category="wrong_command",
            summary=f"The README installs from {wanted}, but the file is called {real}.",
            explanation=f"Point the install command at {real}.",
            evidence=evidence + [Evidence(file=real, line=None, note="actual requirements file")],
            edits=_replace_token_edits(readme_rel, readme_text, wanted, real),
            confidence="high",
        )
    imports = scan_imports(project_dir)
    pkgs = sorted({module_to_package(t, project_dir) for t in imports}, key=str.lower)
    content = "".join(p + "\n" for p in pkgs) or "# no third-party dependencies\n"
    return Diagnosis(
        category="missing_file",
        summary=f"The README installs from {wanted}, but the project has no such file.",
        explanation=(
            f"FirstRun generated {wanted} from the project's third-party imports"
            + (f" ({', '.join(pkgs)})." if pkgs else " (none were found).")
        ),
        evidence=evidence,
        edits=[Edit(path=wanted, old="", new=content)],
        confidence="medium",
    )


def _example_for(project_dir: Path, missing: str) -> Optional[str]:
    path = Path(missing)
    name, stem, suffix = path.name, path.stem, path.suffix
    candidates = [f"{name}.example", f"{name}.sample", f"{name}.template", f"{name}.dist", f"example{name}"]
    if suffix:
        candidates += [f"{stem}.example{suffix}", f"{stem}.sample{suffix}", f"{stem}.template{suffix}"]
    for c in candidates:
        hits = [p for p in project_dir.rglob(c) if not any(part in IGNORED_DIRS for part in p.relative_to(project_dir).parts)]
        if hits:
            return sorted((h.relative_to(project_dir).as_posix() for h in hits), key=len)[0]
    return None


MISSING_PATH_PATTERNS = [
    r"No such file or directory: ['\"]([^'\"]+)['\"]",
    r"[Ff]ile not found:?\s*['\"]?([^\s'\"]+?)['\"]?(?:\s|$)",
    r"['\"]([^'\"]+)['\"] (?:does not exist|was not found|not found)",
    r"(?:[Pp]ath|[Ff]ile) ['\"]?([^\s'\"]+?)['\"]? (?:does not exist|was not found)",
]


def _token_for(tokens: list[str], path: str) -> Optional[str]:
    """The command argument that refers to path (also for --flag=value)."""
    name = Path(path).name
    for t in tokens[1:]:
        value = t.split("=", 1)[1] if t.startswith("-") and "=" in t else t
        if value == path or path.endswith("/" + value) or (name and Path(value).name == name):
            return value
    return None


def _missing_path(failed: StepResult) -> Optional[tuple[str, Optional[str]]]:
    """(missing path, the command argument it came from) for a step that could not find a file."""
    out = failed.output
    tokens = _command_tokens(failed.step.command)
    m = _last(r"(?:FileNotFoundError|IOError|OSError)[^\n]*No such file or directory: ['\"]([^'\"]+)['\"]", out)
    if m:
        return m.group(1), _token_for(tokens, m.group(1))
    # looser messages only count when the path is one of the command's own arguments
    for pattern in MISSING_PATH_PATTERNS:
        for m in reversed(list(re.finditer(pattern, out))):
            path = m.group(1).rstrip(".,:;)")
            token = _token_for(tokens, path)
            if token:
                return path, token
    return None


def _similar_file(project_dir: Path, wanted: str) -> Optional[str]:
    """A project file that looks like the one the README asked for: same extension, close name."""
    want = Path(wanted)
    files = [f for f in list_files(project_dir, limit=3000) if f != wanted]
    if want.suffix:
        files = [f for f in files if Path(f).suffix.lower() == want.suffix.lower()]
    best, best_score = None, 0.0
    for f in files:
        stem, other = want.stem.lower(), Path(f).stem.lower()
        score = difflib.SequenceMatcher(None, stem, other).ratio()
        if len(stem) >= 3 and (stem in other or other in stem):
            score = max(score, 0.75)
        if Path(f).parent.as_posix() == want.parent.as_posix():
            score += 0.1  # same folder as the README expected
        if score >= 0.6 and score > best_score:
            best, best_score = f, score
    return best


def _is_executable_name(name: str, project_dir: Path) -> bool:
    return bool(name) and "/" not in name and not (project_dir / name).exists() and not Path(name).suffix


def _project_frames(output: str, project_dir: Path) -> list[tuple[str, int]]:
    """Traceback frames that point into the project, as (relative path, line)."""
    frames = []
    for m in re.finditer(r'File "([^"]+)", line (\d+)', output):
        parts = Path(m.group(1)).parts
        for i in range(len(parts)):
            rel = Path(*parts[i:])
            if (project_dir / rel).is_file() and not any(p in IGNORED_DIRS for p in rel.parts):
                frames.append((rel.as_posix(), int(m.group(2))))
                break
    return frames


def _prereq_bullet_edits(readme_rel: str, readme_text: str, tool: str) -> list[Edit]:
    """Add `tool` as a bullet at the end of the README's Prerequisites list."""
    lines = readme_text.split("\n")
    heading = None
    for i, line in enumerate(lines):
        h = HEADING_RE.match(line)
        if h and re.search(r"prereq|requirement|before you (?:begin|start)|you(?:'ll| will) need", h.group(2), re.I):
            heading = i
            break
    if heading is None:
        return []
    last_bullet, bullet = None, "- "
    for j in range(heading + 1, len(lines)):
        if HEADING_RE.match(lines[j]):
            break
        b = re.match(r"^(\s*[-*+]\s+)", lines[j])
        if b:
            last_bullet, bullet = j, b.group(1)
    new_line = f"{bullet}`{tool}` installed and on your PATH"
    if last_bullet is None:
        return _line_edits(readme_rel, readme_text, {heading + 1: [lines[heading], "", new_line]})
    return _line_edits(readme_rel, readme_text, {last_bullet + 1: [lines[last_bullet], new_line]})


def output_similarity(documented: str, actual: str) -> float:
    """How close a README's example output is to what really printed, ignoring whitespace."""
    def norm(text: str) -> str:
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("$ ")]
        return " ".join(" ".join(lines).split())

    a, b = norm(documented), norm(actual)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _expect_exit_edits(readme_rel: str, readme_text: str, program: str, code: int) -> list[Edit]:
    """Put `<!-- firstrun: expect-exit N -->` above every block that only runs `program`.

    Exit 0 still counts as passed, so marking every block of the same tool is safe: it only adds
    the tool's own "found problems" code.
    """
    lines = readme_text.split("\n")
    replacements: dict[int, list[str]] = {}
    for b in parse_code_blocks(readme_text):
        commands = [c["command"] for c in _block_commands_of(b)]
        if not commands or any(program_of(c) != program for c in commands):
            continue
        k = b["start"] - 2
        while k >= 0 and not lines[k].strip():
            k -= 1
        if k >= 0 and DIRECTIVE_RE.match(lines[k]):
            continue  # the author already said something about this block
        fence = lines[b["start"] - 1]
        indent = fence[: len(fence) - len(fence.lstrip())]
        replacements[b["start"]] = [f"{indent}<!-- firstrun: expect-exit {code} -->", fence]
    return _line_edits(readme_rel, readme_text, replacements) if replacements else []


def _block_commands_of(block: dict) -> list[dict]:
    from .readme import _block_commands  # noqa: local import, private helper

    return _block_commands(block)


def _rule_expected_exit(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    """A tool that exits 1 on purpose, like a linter run on a broken example."""
    if failed.status != "failed" or failed.exit_code not in (1, 2) or not readme_text:
        return None
    if TRACEBACK_RE.search(failed.output):
        return None
    line_no = _step_line(failed, readme_text)
    documented = documented_output(readme_text, line_no)
    if not documented:
        return None
    score = output_similarity(documented, failed.output)
    if score < 0.5:
        return None
    program = program_of(failed.step.command)
    edits = _expect_exit_edits(readme_rel, readme_text, program, failed.exit_code) if readme_rel else []
    return Diagnosis(
        category="undocumented_step",
        summary=(f"`{failed.step.command}` exits {failed.exit_code} on purpose: its output matches the "
                 "README's example, but nothing says that exit code is expected."),
        explanation=(
            f"The README shows this output (similarity {score:.2f}), so the command did what the author "
            f"meant. A newcomer, a CI job or FirstRun still reads exit {failed.exit_code} as a failure. "
            f"FirstRun marks the blocks that run `{program}` with `<!-- firstrun: expect-exit "
            f"{failed.exit_code} -->`; saying it in the prose helps human readers too."
        ),
        evidence=[Evidence(file=readme_rel or "README", line=line_no, note=f"documented output for exit {failed.exit_code}")],
        edits=edits,
        confidence="medium",
    )


def _rule_missing_executable(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    out = failed.output
    tool, by_code = None, False
    m = _last(r"No such file or directory: ['\"]([^'\"]+)['\"]", out)
    if m and SUBPROCESS_MARKERS.search(out) and _is_executable_name(m.group(1), project_dir):
        tool, by_code = m.group(1), True
    else:
        m = _last(r"(?:^|\s|:\s)([\w.+-]+): (?:command )?not found", out, re.M)
        if m and _is_executable_name(m.group(1), project_dir):
            tool = m.group(1)
    if tool is None:
        return None
    line_no = _step_line(failed, readme_text)
    if tool in HOST_TOOLS:
        return Diagnosis(
            category="platform_issue",
            summary=f"Needs {tool} inside the sandbox, which FirstRun does not provide.",
            explanation=(
                f"`{failed.step.command}` uses {tool}, which needs the host machine itself (a container "
                "runtime, a cluster or a service manager). FirstRun runs every project in a throwaway "
                "sandbox without one, so it stops here instead of guessing. Check this project on a "
                f"machine with {tool}, or document a way to run it without."
            ),
            evidence=[Evidence(file=readme_rel or "README", line=line_no, note=f"`{failed.step.command}`")],
            blocked=True,
            confidence="high",
        )
    from .readme import _prereq_prose  # noqa: local import, private helper

    prose = _prereq_prose(readme_text or "").lower()
    aliases = TOOL_ALIASES.get(tool, (tool,))
    listed = any(re.search(rf"(?<![\w-]){re.escape(a)}(?![\w-])", prose) for a in aliases)
    evidence = [Evidence(file=readme_rel or "README", line=line_no, note=f"`{failed.step.command}`")]
    if by_code:
        frames = _project_frames(out, project_dir)
        if frames:
            evidence.append(Evidence(file=frames[-1][0], line=frames[-1][1], note=f"runs {tool}"))
    who = "The code runs" if by_code else "The README runs"
    if listed:
        return Diagnosis(
            category="platform_issue",
            summary=f"The README lists {tool} as a prerequisite, but the sandbox image does not include it.",
            explanation=(
                "This is a gap in FirstRun's environment rather than a README mistake. Run FirstRun again "
                f"with an image that has {tool} (for example with --image)."
            ),
            evidence=evidence,
            confidence="medium",
        )
    edits = _prereq_bullet_edits(readme_rel, readme_text, tool) if readme_rel and readme_text else []
    return Diagnosis(
        category="platform_issue",
        summary=f"{who} `{tool}`, a system tool the README does not list as a prerequisite.",
        explanation=(
            f"A fresh machine does not have {tool}, so this step fails for a newcomer. "
            + ("Adding it to the Prerequisites list tells them to install it first."
               if edits else "Mention it in the README so newcomers install it first.")
        ),
        evidence=evidence,
        edits=edits,
        confidence="medium" if edits else "high",
    )


def _rule_missing_file(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    found = _missing_path(failed)
    if not found:
        return None
    missing, token = found
    if SUBPROCESS_MARKERS.search(failed.output) and _is_executable_name(missing, project_dir):
        return None  # a program, handled by _rule_missing_executable
    name = Path(missing).name
    line_no = _step_line(failed, readme_text)
    evidence = [Evidence(file=readme_rel or "README", line=line_no, note=f"`{failed.step.command}` needs {name}")]
    example = _example_for(project_dir, name)
    if example:
        target = (Path(example).parent / name).as_posix() if Path(example).parent.as_posix() != "." else name
        cmd = f"cp {example} {target}"
        edits = _insert_before(readme_rel, readme_text, line_no, cmd) if readme_rel and readme_text and line_no else []
        return Diagnosis(
            category="undocumented_step",
            summary=f"The program needs {target}, which the README never tells you to create from {example}.",
            explanation=f"Add `{cmd}` before `{failed.step.command}`.",
            evidence=evidence + [Evidence(file=example, line=None, note="template for the missing file")],
            edits=edits,
            confidence="high" if edits else "medium",
        )
    if token and readme_rel and readme_text:
        hits = [p.relative_to(project_dir).as_posix() for p in project_dir.rglob(name)
                if not any(part in IGNORED_DIRS for part in p.relative_to(project_dir).parts)]
        hits = [h for h in hits if h != token]
        if hits:
            real = sorted(hits, key=len)[0]
            return Diagnosis(
                category="wrong_command",
                summary=f"The README passes `{token}`, but that file is at `{real}`.",
                explanation=f"Point the documented command at {real}.",
                evidence=evidence + [Evidence(file=real, line=None, note="actual file")],
                edits=_replace_token_edits(readme_rel, readme_text, token, real),
                confidence="high",
            )
        similar = _similar_file(project_dir, token)
        if similar:
            return Diagnosis(
                category="missing_file",
                summary=f"The README passes `{token}`, which is not in the project. The closest file is `{similar}`.",
                explanation=(
                    f"`{failed.step.command}` cannot run as written. FirstRun points the example at {similar}; "
                    f"if {token} was meant to be committed, add it instead."
                ),
                evidence=evidence + [Evidence(file=similar, line=None, note="closest existing file")],
                edits=_replace_token_edits(readme_rel, readme_text, token, similar),
                confidence="medium",
            )
    shown = token or missing
    return Diagnosis(
        category="missing_file",
        summary=f"`{failed.step.command}` needs `{shown}`, which is not in the project and no README step creates it.",
        explanation="Commit the file, or point the README at a file that exists, so the example runs as written.",
        evidence=evidence,
        confidence="high",
    )


def _rule_pin(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(
        r"(?:No matching distribution found for|Could not find a version that satisfies the requirement)\s+"
        r"([A-Za-z0-9][A-Za-z0-9._\[\],-]*)\s*((?:==|>=|<=|~=|!=|>|<)[^\s;)]+)",
        failed.output,
    )
    if not m:
        return None
    name, spec = m.group(1), m.group(2)
    base = normalize(name.split("[")[0])
    for path in _requirements_files(project_dir):
        text = read_text(path) or ""
        for raw in text.split("\n"):
            req = _req_name(raw)
            if req and normalize(req) == base and re.search(r"(==|>=|<=|~=|!=|>|<)", raw):
                rel = path.relative_to(project_dir).as_posix()
                loose = re.split(r"\s*(?:==|>=|<=|~=|!=|>|<)", raw.strip(), 1)[0]
                old = raw + "\n" if raw + "\n" in text else raw
                new = loose + "\n" if old.endswith("\n") else loose
                return Diagnosis(
                    category="dependency_pin",
                    summary=f"{rel} pins `{name}{spec}`, which pip cannot find for this Python.",
                    explanation=(
                        "The pinned version does not exist on PyPI or has no build for the sandbox's Python. "
                        "FirstRun loosens the pin as a starting point; choose a real version before merging."
                    ),
                    evidence=[Evidence(file=rel, line=text.split("\n").index(raw) + 1, note=raw.strip())],
                    edits=[Edit(path=rel, old=old, new=new)],
                    confidence="low",
                )
    return Diagnosis(
        category="dependency_pin",
        summary=f"pip cannot find `{name}{spec}` for this Python.",
        explanation="The pin is not in a requirements file FirstRun can edit.",
        confidence="low",
    )


def _rule_python_version(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(r"requires a different Python: ([\d.]+) not in ['\"]([^'\"]+)['\"]", failed.output)
    if m:
        return Diagnosis(
            category="platform_issue",
            summary=f"A package requires Python {m.group(2)}, but the sandbox runs {m.group(1)}.",
            explanation="Document the supported Python version in the README prerequisites.",
            confidence="medium",
        )
    if re.search(r"^\s*SyntaxError:", failed.output, re.M):
        return Diagnosis(
            category="platform_issue",
            summary="Python reported a SyntaxError, which often means the code needs a newer Python than the sandbox has.",
            explanation=_tail(failed.output, 8),
            confidence="low",
        )
    return None


def _rule_interactive(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    if not re.search(r"EOFError: EOF when reading a line|EOFError", failed.output):
        return None
    line_no = _step_line(failed, readme_text)
    return Diagnosis(
        category="interactive_input",
        summary=f"`{failed.step.command}` waits for keyboard input, so it cannot be checked unattended.",
        explanation=(
            "The program called input() and got end-of-file. Document a non-interactive example, for "
            "instance passing the input as an argument or piping it with echo."
        ),
        evidence=[Evidence(file=readme_rel or "README", line=line_no, note="interactive command")],
        confidence="medium",
    )


def _rule_permission(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    m = _last(r"(\./[\w./-]+): Permission denied", failed.output)
    if not m:
        return None
    script = m.group(1)
    line_no = _step_line(failed, readme_text)
    edits = _insert_before(readme_rel, readme_text, line_no, f"chmod +x {script}") if readme_rel and readme_text and line_no else []
    return Diagnosis(
        category="undocumented_step",
        summary=f"{script} is not executable in a fresh clone.",
        explanation=f"Add `chmod +x {script}` to the README (or commit the file with its executable bit).",
        evidence=[Evidence(file=readme_rel or "README", line=line_no, note=f"runs {script}")],
        edits=edits,
        confidence="medium",
    )


def _rule_timeout(project_dir, plan, run, failed, readme_rel, readme_text) -> Optional[Diagnosis]:
    if failed.status != "timeout":
        return None
    return Diagnosis(
        category="unknown",
        summary=f"`{failed.step.command}` did not finish within the time limit.",
        explanation=(
            "It may be waiting for input, starting a server that was not recognised as long running, or "
            "downloading something large. Check the log tail for the last thing it printed."
        ),
        confidence="low",
    )


RULES = [
    _rule_expected_exit,
    _rule_missing_module,
    _rule_credentials,
    _rule_requirements_file,
    _rule_command_not_found,
    _rule_cant_open,
    _rule_missing_executable,
    _rule_missing_file,
    _rule_pin,
    _rule_python_version,
    _rule_interactive,
    _rule_permission,
    _rule_timeout,
]


def diagnose(project_dir: Path, plan: Plan, run: RunResult) -> Optional[Diagnosis]:
    """Explain the first failure of a run with deterministic rules, or None if none apply."""
    failed = run.failed_step
    if failed is None:
        return None
    readme_rel, readme_text = _readme(project_dir, plan)
    for rule in RULES:
        diagnosis = rule(project_dir, plan, run, failed, readme_rel, readme_text)
        if diagnosis is not None:
            diagnosis.engine = "rules"
            return diagnosis
    return None

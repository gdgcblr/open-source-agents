"""Functionality & reproducibility (static part): will it install and run on someone else's machine?

The LLM review adds the claims-vs-code verdicts on top of these checks.
"""

from __future__ import annotations

import ast
import json
import re

from judge.analyzers import manifest, pyast
from judge.models import AnalyzerResult, Check, Finding
from judge.workspace import Workspace

DIM = "functionality"
NODE_BUILTINS = {
    "fs",
    "path",
    "http",
    "https",
    "url",
    "crypto",
    "os",
    "child_process",
    "events",
    "stream",
    "util",
    "readline",
    "zlib",
    "net",
    "tls",
    "dns",
    "assert",
    "buffer",
    "process",
    "querystring",
    "worker_threads",
    "timers",
    "perf_hooks",
    "module",
    "cluster",
    "vm",
    "string_decoder",
    "tty",
    "v8",
}
IGNORED_ENV = {
    "HOME",
    "PATH",
    "USER",
    "PWD",
    "TERM",
    "CI",
    "PYTHONPATH",
    "NODE_ENV",
    "SHELL",
    "TMPDIR",
    "LANG",
    "VIRTUAL_ENV",
    "PYTEST_CURRENT_TEST",
}
DEV_ONLY = {"pytest", "pytest-asyncio", "pytest-mock", "mypy", "ruff", "black", "pytest-cov"}
# Packages reliably installed by a declared parent (ADK ships google-genai, FastAPI ships pydantic…).
# Importing them without declaring them works, so we don't count it as a reproducibility failure.
TRANSITIVE: dict[str, set[str]] = {
    "google-genai": {
        "google-adk",
        "langchain-google-genai",
        "google-cloud-aiplatform",
        "llama-index-llms-google-genai",
    },
    "pydantic": {
        "fastapi",
        "google-adk",
        "openai",
        "google-genai",
        "anthropic",
        "langchain-core",
        "langchain",
        "pydantic-settings",
        "crewai",
        "mcp",
        "fastmcp",
        "pydantic-ai",
        "groq",
        "instructor",
        "litellm",
    },
    "httpx": {"openai", "anthropic", "google-genai", "google-adk", "groq", "mcp", "fastmcp", "langsmith", "ollama"},
    "starlette": {"fastapi", "mcp", "fastmcp", "sse-starlette"},
    "anyio": {"httpx", "openai", "anthropic", "starlette", "fastapi", "mcp"},
    "typing-extensions": {"pydantic", "fastapi", "openai", "anthropic", "google-genai"},
    "requests": {"google-generativeai", "langchain", "langchain-community", "huggingface-hub", "transformers"},
    "google-api-core": {"google-generativeai", "google-cloud-aiplatform", "google-adk"},
    "google-auth": {"google-generativeai", "google-genai", "google-adk", "google-api-python-client"},
    "jinja2": {"fastapi", "flask"},
    "werkzeug": {"flask"},
    "numpy": {"pandas", "scikit-learn", "transformers", "sentence-transformers", "faiss-cpu", "chromadb"},
    "langchain-core": {"langchain", "langgraph", "langchain-openai", "langchain-google-genai", "langchain-community"},
    "uvicorn": {"fastapi[standard]", "mcp", "fastmcp", "google-adk", "chainlit"},
    "click": {"typer", "uvicorn", "flask"},
    "rich": {"typer"},
    "python-dotenv": {"google-adk", "crewai", "litellm", "pydantic-settings[dotenv]"},
    "yarl": {"aiohttp"},
}
NPM_NAME = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*(/[\w./-]*)?$")
JS_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\s*\(\s*|^\s*import\s+)['"]([^'".][^'"]*)['"]""", re.M)
ENV_EXAMPLE_KEY = re.compile(r"^\s*#?\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", re.M)
JS_ENV = re.compile(r"(?:process\.env\.|import\.meta\.env\.)([A-Z][A-Z0-9_]*)|process\.env\[['\"]([A-Z0-9_]+)['\"]\]")
CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.S)
ABS_PATH = re.compile(r"""(['"])(/Users/[^'"]+|/home/[^'"]+|[A-Za-z]:\\\\[^'"]+)\1""")
RUN_PATTERNS = [
    re.compile(r"\b(?:python3?|py|uv run(?: python)?)\s+(?:-u\s+)?(?!-m\b)([\w./-]+\.py)\b"),
    re.compile(r"\b(?:python3?|py|uv run(?: python)?)\s+-m\s+([\w.]+)"),
    re.compile(r"\buvicorn\s+([\w.]+):\w+"),
    re.compile(r"\b(?:streamlit|chainlit|gradio)\s+run\s+([\w./-]+\.py)"),
    re.compile(r"\bfastapi\s+(?:dev|run)\s+([\w./-]+\.py)"),
    re.compile(r"\bnode\s+([\w./-]+\.[cm]?js)\b"),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(start|dev|serve|build)\b"),
    re.compile(r"\badk\s+(web|run|api_server)\b"),
    re.compile(r"\b(go run|cargo run|docker compose up|docker run)\b"),
]


def _local_modules(ws: Workspace) -> set[str]:
    """Lower-cased module/package names that resolve inside the project (imports are case-insensitive on
    macOS/Windows, and projects are often run from their parent folder as a package)."""
    names: set[str] = {ws.slug.lower(), ws.slug.lower().replace("-", "_")}
    for f in ws.files:
        parts = f.lstrip("/").split("/")
        for i, part in enumerate(parts):
            if part.endswith(".py"):
                names.add(part[:-3].lower())
            elif i < len(parts) - 1:
                names.add(part.lower().replace("-", "_"))
    return names


def _optional_import_lines(tree: ast.Module) -> set[int]:
    """Lines of imports guarded by `try: ... except ImportError`."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            h.type is not None and re.search(r"ImportError|ModuleNotFoundError|Exception", ast.unparse(h.type))
            for h in node.handlers
        ):
            for sub in node.body:
                for n in ast.walk(sub):
                    if isinstance(n, (ast.Import, ast.ImportFrom)):
                        lines.add(n.lineno)
    return lines


def python_env_vars(ws: Workspace) -> dict[str, tuple[str, int]]:
    found: dict[str, tuple[str, int]] = {}
    for rel in ws.py_files:
        tree = ws.ast(rel)
        if tree is None:
            continue
        aliases = pyast.alias_map(tree)
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Call):
                q = pyast.qualname(node, aliases) or ""
                if (
                    q.endswith(("os.getenv", "os.environ.get", "environ.get", "getenv", "os.environ.setdefault"))
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    name = node.args[0].value
            elif isinstance(node, ast.Subscript) and (pyast.dotted(node.value) or "").endswith("environ"):
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    name = node.slice.value
            if name and name not in IGNORED_ENV and name not in found:
                found[name] = (rel, node.lineno)
    for rel, line, _, m in ws.grep(JS_ENV, ws.js_files + ws.files_by_language("HTML")):
        name = m.group(1) or m.group(2)
        if name and name not in IGNORED_ENV and name not in found:
            found[name] = (rel, line)
    return found


def documented_env_vars(ws: Workspace) -> set[str]:
    keys: set[str] = set()
    for rel in ws.files:
        if re.search(r"(^|/)\.env\.(example|sample|template)$", rel):
            keys |= set(ENV_EXAMPLE_KEY.findall(ws.read(rel) or ""))
    return keys


def analyze(ws: Workspace) -> AnalyzerResult:
    r = AnalyzerResult()
    m = manifest.parse(ws)

    # R1 manifest
    has_external = bool(ws.code_files)
    r.checks.append(
        Check(
            id="manifest",
            dimension=DIM,
            label="Dependency manifest present and parseable",
            weight=2,
            status="fail" if (not m.files and has_external) or m.errors else "pass",
            detail="; ".join(m.errors) if m.errors else ", ".join(m.files) or "No code, no manifest needed",
            fix="Add requirements.txt / pyproject.toml / package.json listing every dependency."
            if not m.files
            else None,
        )
    )

    # R2 imports vs declared dependencies
    declared = m.python_names
    local = _local_modules(ws)
    undeclared: dict[str, tuple[str, int]] = {}
    for rel in ws.py_files:
        tree = ws.ast(rel)
        if tree is None:
            continue
        optional = _optional_import_lines(tree)
        for imp in pyast.imports(tree):
            top = imp.module.split(".")[0]
            if top in pyast.STDLIB or top.lower() in local or imp.line in optional or imp.module == "google":
                continue  # `google` alone is a namespace package; its submodules are checked individually
            dist = pyast.normalize_dist(pyast.dist_name(imp.module))
            if dist in declared or pyast.normalize_dist(top) in declared or declared & TRANSITIVE.get(dist, set()):
                continue
            if dist != "google-genai" and any(d.startswith(dist) or dist.startswith(d) for d in declared if len(d) > 3):
                continue  # e.g. langchain_community vs langchain-community[extras]; google-genai ≠ google-generativeai
            if dist in DEV_ONLY and ws.is_test_file(rel):
                continue
            undeclared.setdefault(dist, (rel, imp.line))
    npm = m.npm_names
    for rel, line, _, mm in ws.grep(JS_IMPORT, ws.js_files):
        spec = mm.group(1)
        if spec.startswith(("node:", "http:", "https:", "/", "~", "@/")) or not NPM_NAME.match(spec):
            continue
        pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
        if pkg in NODE_BUILTINS or pkg in npm:
            continue
        undeclared.setdefault(pkg, (rel, line))
    n = len(undeclared)
    r.checks.append(
        Check(
            id="deps_declared",
            dimension=DIM,
            label="Every imported package is declared in the manifest",
            weight=3,
            status="pass" if n == 0 else "warn" if n == 1 else "fail",
            score=max(0.0, 1 - 0.34 * n),
            detail="Undeclared: " + ", ".join(sorted(undeclared)) if undeclared else "All imports resolved",
            fix=f"Add {', '.join(sorted(undeclared)[:5])} to your manifest." if undeclared else None,
        )
    )
    for dist, (rel, line) in sorted(undeclared.items()):
        r.findings.append(
            Finding(
                dimension=DIM,
                severity="medium",
                title=f"Undeclared dependency: {dist}",
                file=rel,
                line=line,
                detail="A clean install will fail with ImportError.",
                fix=f"Add `{dist}` to the dependency manifest.",
            )
        )

    # R3 env vars documented
    used = python_env_vars(ws)
    documented = documented_env_vars(ws)
    readme = ws.readme
    missing = {k: v for k, v in used.items() if k not in documented and k not in readme}
    if used:
        ratio = 1 - len(missing) / len(used)
        r.checks.append(
            Check(
                id="env_documented",
                dimension=DIM,
                label="Env vars read by the code are documented (.env.example/README)",
                weight=2,
                status="pass" if not missing else "warn" if ratio >= 0.5 else "fail",
                score=ratio,
                detail=f"{len(used) - len(missing)}/{len(used)} documented"
                + (f"; missing: {', '.join(sorted(missing))}" if missing else ""),
                fix="Add the missing variables to .env.example with placeholder values." if missing else None,
            )
        )
        for k, (rel, line) in sorted(missing.items()):
            r.findings.append(
                Finding(
                    dimension=DIM,
                    severity="low",
                    title=f"Undocumented env var {k}",
                    file=rel,
                    line=line,
                    fix=f"Add `{k}=` to .env.example.",
                )
            )
    else:
        r.checks.append(
            Check(
                id="env_documented",
                dimension=DIM,
                label="Env vars read by the code are documented",
                weight=2,
                status="skip",
                detail="Code reads no environment variables",
            )
        )

    # R4 run command in README resolves
    commands = _run_targets(readme)
    resolved = [c for c in commands if _resolves(ws, c)]
    if not commands:
        st, detail = "warn", "No run command found in README code blocks"
    else:
        st = "pass" if resolved else "fail"
        detail = (
            f"Resolved: {', '.join(c[1] for c in resolved[:3])}"
            if resolved
            else f"Targets not found: {', '.join(c[1] for c in commands[:3])}"
        )
    r.checks.append(
        Check(
            id="run_command",
            dimension=DIM,
            label="README run command points at real files",
            weight=2,
            status=st,
            detail=detail,
            fix=None if st == "pass" else "Add an exact, copy-pasteable run command to 'How to Run'.",
        )
    )

    # R5 code compiles
    broken = [f for f in ws.py_files if ws.ast(f) is None and ws.read(f) is not None]
    for f in ws.files:
        if f.endswith(".json") and not f.endswith(".ipynb"):
            try:
                json.loads(ws.read(f) or "null")
            except json.JSONDecodeError:
                broken.append(f)
    r.checks.append(
        Check(
            id="compiles",
            dimension=DIM,
            label="All Python/JSON files parse",
            weight=2,
            status="fail" if broken else "pass" if ws.py_files or ws.js_files else "skip",
            detail="Broken: " + ", ".join(broken) if broken else f"{len(ws.py_files)} Python file(s) OK",
        )
    )
    for f in broken:
        r.findings.append(
            Finding(
                dimension=DIM,
                severity="high",
                title="File does not parse",
                file=f,
                fix="Fix the syntax error; the project cannot run.",
            )
        )

    # R6 install instructions match the manifest
    names = {f.rsplit("/", 1)[-1].lower() for f in m.files}
    expected = []
    if "requirements.txt" in names:
        expected.append(r"pip3?\s+install\s+(-r|--requirement)\s+\S*requirements|uv\s+pip\s+install\s+-r")
    if "pyproject.toml" in names:
        expected.append(r"pip3?\s+install\s+(-e\s+)?[.\"']|uv\s+(sync|pip\s+install)|poetry\s+install")
    if "package.json" in names:
        expected.append(r"\b(npm|pnpm|yarn|bun)\s+(install|i|ci)\b")
    if expected:
        ok = any(re.search(p, readme) for p in expected)
        r.checks.append(
            Check(
                id="install_steps",
                dimension=DIM,
                label="README install steps match the manifest",
                weight=1,
                status="pass" if ok else "warn",
                detail="Install command found" if ok else "No matching install command in README",
                fix=None if ok else "Document the exact install command (e.g. pip install -r requirements.txt).",
            )
        )

    # R7 machine-specific paths
    abs_hits = list(ws.grep(ABS_PATH, ws.source_files))
    r.checks.append(
        Check(
            id="portable_paths",
            dimension=DIM,
            label="No machine-specific absolute paths",
            weight=1,
            status="warn" if abs_hits else "pass",
            detail=f"{len(abs_hits)} hard-coded path(s)" if abs_hits else "None found",
        )
    )
    for rel, line, text, _ in abs_hits[:5]:
        r.findings.append(
            Finding(
                dimension=DIM,
                severity="low",
                title="Hard-coded absolute path",
                file=rel,
                line=line,
                snippet=text.strip()[:160],
                fix="Use paths relative to the project or env vars.",
            )
        )

    r.facts.update(
        env_vars=sorted(used),
        env_documented=sorted(documented),
        undeclared=sorted(undeclared),
        run_commands=[c[1] for c in commands],
    )
    return r


def _run_targets(readme: str) -> list[tuple[str, str]]:
    """(kind, target) pairs for run commands found in README code blocks."""
    out: list[tuple[str, str]] = []
    for block in CODE_BLOCK.findall(readme):
        for line in block.splitlines():
            line = line.strip().lstrip("$> ").strip()
            if not line or line.startswith("#"):
                continue
            for i, pat in enumerate(RUN_PATTERNS):
                mm = pat.search(line)
                if mm:
                    kind = ["file", "module", "module", "file", "file", "file", "npm", "adk", "other"][i]
                    out.append((kind, mm.group(1)))
                    break
    return list(dict.fromkeys(out))


def _resolves(ws: Workspace, cmd: tuple[str, str]) -> bool:
    kind, target = cmd
    prefix = ws.project_path.rstrip("/") + "/"
    if kind == "file":
        t = target.removeprefix("./").removeprefix(prefix)
        return ws.exists(t) or any(f.endswith("/" + t) for f in ws.files)
    if kind == "module":
        base = target.replace(".", "/")
        return any(ws.exists(p) for p in (f"{base}.py", f"{base}/__main__.py", f"{base}/__init__.py")) or any(
            f.endswith(f"/{base}.py") or f.endswith(f"/{base}/__main__.py") for f in ws.files
        )
    if kind == "npm":
        pkg = ws.find("package.json")
        try:
            scripts = json.loads(ws.read(pkg) or "{}").get("scripts", {}) if pkg else {}
        except json.JSONDecodeError:
            return False
        return target in scripts
    if kind == "adk":
        return any(f.endswith("agent.py") for f in ws.files)
    return True

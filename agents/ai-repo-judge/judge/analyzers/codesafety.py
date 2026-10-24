"""Dangerous code patterns (Python via the AST, JS/HTML via patterns) and AI-specific risks:
model output reaching code execution, unbounded agent loops and provider keys exposed to browsers."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable

from judge.analyzers import pyast
from judge.models import Finding
from judge.workspace import FRONTEND_EXTS, Workspace

DIM = "security"
Risk = tuple[str, str, str]  # (severity, title, fix)

AI_MODULE_PREFIXES = (
    "google.generativeai", "google.genai", "google.adk", "openai", "anthropic", "groq", "ollama", "langchain",
    "langgraph", "crewai", "agents", "mcp", "fastmcp", "litellm", "llama_index", "mistralai", "cohere", "vertexai",
    "transformers", "huggingface_hub", "smolagents", "pydantic_ai", "autogen", "dspy", "haystack", "semantic_kernel",
    "together",
)  # fmt: skip
UNSAFE_DESERIALISE = {"pickle.load", "pickle.loads", "dill.load", "dill.loads", "marshal.loads", "shelve.open"}
LOOP_LIMIT = re.compile(r"(?i)max_?(steps|iter|iterations|turns|rounds|calls)|step|iteration|attempt")

BROWSER_LLM = re.compile(
    r"(generativelanguage\.googleapis\.com|api\.openai\.com|api\.groq\.com|"
    r"api\.anthropic\.com|openrouter\.ai/api|api\.mistral\.ai)"
)
FRONTEND_DIRS = {"web", "static", "public", "frontend", "client", "www", "ui", "templates"}
JS_RISKS = [
    (re.compile(r"\beval\s*\("), "high", "Dynamic code execution (eval)", "Avoid eval; parse data with JSON.parse."),
    (re.compile(r"\bnew\s+Function\s*\("), "high", "Dynamic code execution (new Function)",
     "Avoid building functions from strings."),
    (re.compile(r"\bdangerouslySetInnerHTML\b"), "low", "dangerouslySetInnerHTML used",
     "Sanitise HTML (e.g. DOMPurify) before rendering it."),
    (re.compile(r"\.innerHTML\s*\+?=(?!\s*(['\"`])\s*\1)"), "medium",
     "innerHTML assignment (XSS if it renders model or user text)",
     "Use textContent, or sanitise with DOMPurify before inserting model output."),
    (re.compile(r"child_process.*\bexec(Sync)?\s*\(|\bexecSync\s*\("), "medium", "Shell command execution",
     "Use execFile/spawn with an argument list and validate inputs."),
]  # fmt: skip


def imports_ai(tree: ast.Module) -> bool:
    return any(i.module.startswith(AI_MODULE_PREFIXES) for i in pyast.imports(tree))


def dynamic_command(call: ast.Call) -> bool:
    """A subprocess call whose executable isn't fixed: shell=True, or a command that isn't a literal list
    starting with a constant (["git", ...] is the safe pattern)."""
    if pyast.is_const(pyast.kwarg(call, "shell"), True):
        return True
    first = call.args[0] if call.args else pyast.kwarg(call, "args")
    if isinstance(first, (ast.List, ast.Tuple)):
        return not (first.elts and isinstance(first.elts[0], ast.Constant))
    return first is not None and not isinstance(first, ast.Constant)


def _formatted_string(node: ast.AST | None) -> bool:
    """f-strings, `"..." % x`, `"..." + x` and `"...".format(x)`: the usual SQL-injection shapes."""
    if isinstance(node, (ast.JoinedStr, ast.BinOp)):
        return True
    return isinstance(node, ast.Call) and (pyast.dotted(node.func) or "").endswith(".format")


# ---- one small rule per dangerous call shape -------------------------------------------------------
def _exec(q: str, call: ast.Call) -> Risk | None:
    if q in ("eval", "exec"):
        return "high", f"Dynamic code execution ({q})", "Avoid eval/exec; use ast.literal_eval or a safe parser."
    return None


def _shell(q: str, call: ast.Call) -> Risk | None:
    literal = pyast.is_const(call.args[0] if call.args else None)
    if q in ("os.system", "os.popen"):
        return ("medium" if literal else "high"), f"Shell command via {q}", "Use subprocess.run([...]) without a shell."
    if q.startswith("subprocess.") and pyast.is_const(pyast.kwarg(call, "shell"), True):
        return (
            ("medium" if literal else "high"),
            "subprocess with shell=True",
            "Pass an argument list; drop shell=True.",
        )
    return None


def _deserialise(q: str, call: ast.Call) -> Risk | None:
    if q in UNSAFE_DESERIALISE:
        return "medium", f"Unsafe deserialisation ({q})", "Use JSON for untrusted data."
    loader = pyast.kwarg(call, "Loader")
    if q == "yaml.unsafe_load" or (q == "yaml.load" and (loader is None or "Safe" not in ast.unparse(loader))):
        return "medium", "yaml.load without SafeLoader", "Use yaml.safe_load."
    return None


def _transport(q: str, call: ast.Call) -> Risk | None:
    if pyast.is_const(pyast.kwarg(call, "verify"), False):
        return "medium", "TLS certificate verification disabled", "Remove verify=False."
    if q == "tempfile.mktemp":
        return "low", "Insecure tempfile.mktemp", "Use tempfile.NamedTemporaryFile."
    return None


def _sql(q: str, call: ast.Call) -> Risk | None:
    if q.rsplit(".", 1)[-1] in ("execute", "executemany", "executescript") and _formatted_string(
        call.args[0] if call.args else None
    ):
        return "medium", "SQL built with string formatting", "Use parameterised queries (cursor.execute(sql, params))."
    return None


def _server(q: str, call: ast.Call) -> Risk | None:
    last = q.rsplit(".", 1)[-1]
    if last == "run" and pyast.is_const(pyast.kwarg(call, "debug"), True):
        return "medium", "Debug server enabled", "Read debug from an env var; default off."
    if last == "add_middleware" and any("CORS" in (pyast.dotted(a) or "") for a in call.args):
        origins = pyast.kwarg(call, "allow_origins")
        if origins is not None and "'*'" in ast.unparse(origins):
            return "low", "CORS allows every origin", "List the allowed origins explicitly."
    return None


CALL_RULES: list[Callable[[str, ast.Call], Risk | None]] = [_exec, _shell, _deserialise, _transport, _sql, _server]


def _finding(sev: str, title: str, rel: str, node: ast.AST, text: str, fix: str, detail: str = "") -> Finding:
    line = getattr(node, "lineno", 1)
    return Finding(dimension=DIM, severity=sev, title=title, file=rel, line=line, snippet=pyast.segment(text, line),
                   fix=fix, detail=detail)  # type: ignore[arg-type]  # fmt: skip


def _ai_risks(rel: str, tree: ast.Module, text: str, aliases: dict[str, str]) -> list[Finding]:
    """Model output flowing into code execution, and `while True` agent loops with no step limit."""
    out: list[Finding] = []
    framework = pyast.llm_framework_imported(tree)
    for fn in pyast.functions(tree):
        fn_calls = list(pyast.calls(fn, aliases))
        execs = [c for c, q in fn_calls if q in ("eval", "exec", "os.system", "os.popen")
                 or (q.startswith("subprocess.") and dynamic_command(c))]  # fmt: skip
        if execs and any(pyast.is_llm_call(q, framework) for _, q in fn_calls):
            out.append(_finding("high", "Model output may reach code execution", rel, execs[0], text,
                                "Never execute model output; allow-list actions and require human confirmation.",
                                f"`{fn.name}` calls an LLM and executes code/commands in the same function."))  # fmt: skip
    for node in ast.walk(tree):
        if not (isinstance(node, ast.While) and pyast.is_const(node.test, True)):
            continue
        if not any(pyast.is_llm_call(q, framework) for _, q in pyast.calls(node, aliases)):
            continue
        has_exit = any(isinstance(n, (ast.Break, ast.Return)) for n in ast.walk(node))
        if not has_exit or not LOOP_LIMIT.search(ast.unparse(node)):
            out.append(_finding("low" if has_exit else "medium", "Agent loop without an explicit step limit", rel,
                                node, text, "Cap iterations (e.g. MAX_STEPS) to bound cost and runaway tool use."))  # fmt: skip
    return out


def python_risks(ws: Workspace) -> list[Finding]:
    found: list[Finding] = []
    for rel in ws.py_files:
        tree, text = ws.ast(rel), ws.read(rel) or ""
        if tree is None:
            continue
        aliases = pyast.alias_map(tree)
        for call, q in pyast.calls(tree, aliases):
            risk = next((r for rule in CALL_RULES if (r := rule(q, call))), None)
            if risk:
                found.append(_finding(risk[0], risk[1], rel, call, text, risk[2]))
        if imports_ai(tree):
            found.extend(_ai_risks(rel, tree, text, aliases))
    return found


def _is_frontend(rel: str, ext: str) -> bool:
    return ext == ".html" or bool(FRONTEND_DIRS & set(rel.lower().split("/")[:-1]))


def js_risks(ws: Workspace) -> list[Finding]:
    found: list[Finding] = []
    for rel in ws.files:
        ext = "." + rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if ext not in FRONTEND_EXTS:
            continue
        frontend = _is_frontend(rel, ext)
        for i, line in enumerate((ws.read(rel) or "").splitlines(), 1):
            snippet = line.strip()[:200]
            found.extend(Finding(dimension=DIM, severity=sev, title=title, file=rel, line=i, snippet=snippet, fix=fix)
                         for pat, sev, title, fix in JS_RISKS if pat.search(line))  # type: ignore[arg-type]  # fmt: skip
            if frontend and BROWSER_LLM.search(line):
                found.append(Finding(dimension=DIM, severity="high", title="LLM API called from browser code", file=rel,
                                     line=i, snippet=snippet, detail="Calling the provider from the browser exposes the API key.",
                                     fix="Proxy model calls through your backend and keep the key server-side."))  # fmt: skip
    return found

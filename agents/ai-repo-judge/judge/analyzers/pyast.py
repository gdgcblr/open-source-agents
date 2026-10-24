"""Python AST helpers: alias-aware call names, import collection, LLM-call detection."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass

STDLIB = set(sys.stdlib_module_names) | {"__future__"}

# Import name -> PyPI distribution name, for the common cases where they differ.
IMPORT_TO_DIST: dict[str, str] = {
    "google.generativeai": "google-generativeai",
    "google.genai": "google-genai",
    "google.adk": "google-adk",
    "google.cloud": "google-cloud",
    "vertexai": "google-cloud-aiplatform",
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "fitz": "pymupdf",
    "PyPDF2": "pypdf2",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "dateutil": "python-dateutil",
    "jwt": "pyjwt",
    "attr": "attrs",
    "Crypto": "pycryptodome",
    "serial": "pyserial",
    "magic": "python-magic",
    "telegram": "python-telegram-bot",
    "discord": "discord.py",
    "github": "pygithub",
    "git": "gitpython",
    "agents": "openai-agents",
    "mcp": "mcp",
    "fastmcp": "fastmcp",
    "multipart": "python-multipart",
    "jose": "python-jose",
    "slack_sdk": "slack-sdk",
    "googleapiclient": "google-api-python-client",
    "llama_index": "llama-index",
    "langchain_google_genai": "langchain-google-genai",
    "sentence_transformers": "sentence-transformers",
    "huggingface_hub": "huggingface-hub",
    "duckduckgo_search": "duckduckgo-search",
    "ddgs": "ddgs",
    "speech_recognition": "speechrecognition",
    "pydantic_settings": "pydantic-settings",
    "pydantic_ai": "pydantic-ai",
    "tavily": "tavily-python",
    "pymupdf4llm": "pymupdf4llm",
}

LLM_METHODS = {
    "generate_content",
    "generate_content_async",
    "generate_content_stream",
    "send_message",
    "send_message_stream",
    "completion",
    "acompletion",
    "kickoff",
    "kickoff_async",
}
LLM_CREATE_CONTEXT = ("completions", "messages", "responses", "chat")
FRAMEWORK_METHODS = {"invoke", "ainvoke", "stream", "astream", "run", "run_sync", "run_async", "run_streamed"}
# Generic method names (run/invoke/stream) only count as model calls when an agent framework is imported;
# MCP servers also have .run(), so MCP alone doesn't qualify.
LLM_FRAMEWORKS = (
    "langchain",
    "langgraph",
    "crewai",
    "agents",
    "google.adk",
    "llama_index",
    "autogen",
    "smolagents",
    "pydantic_ai",
    "dspy",
    "haystack",
    "semantic_kernel",
    "litellm",
)


def llm_framework_imported(tree: ast.Module) -> bool:
    return any(i.module == p or i.module.startswith(p + ".") for i in imports(tree) for p in LLM_FRAMEWORKS)


def dist_name(import_name: str) -> str:
    """Best-effort distribution name for a top-level (or dotted) import."""
    for key in (import_name, ".".join(import_name.split(".")[:2]), import_name.split(".")[0]):
        if key in IMPORT_TO_DIST:
            return IMPORT_TO_DIST[key]
    return import_name.split(".")[0]


def normalize_dist(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


@dataclass
class Import:
    module: str  # fully qualified module, e.g. "google.genai"
    line: int


def imports(tree: ast.Module) -> list[Import]:
    out: list[Import] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(Import(a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(Import(node.module, node.lineno))
            # `from google import genai` imports the submodule google.genai
            out.extend(
                Import(f"{node.module}.{a.name}", node.lineno)
                for a in node.names
                if node.module in ("google", "google.cloud", "langchain", "llama_index")
            )
    return out


def alias_map(tree: ast.Module) -> dict[str, str]:
    """Local name -> qualified name for imports in this module."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                names[a.asname or a.name] = f"{node.module}.{a.name}"
    return names


def dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        inner = dotted(node.func)
        if inner is None:
            return None
        parts.append(inner + "()")
    else:
        return None
    return ".".join(reversed(parts))


def qualname(call: ast.Call, aliases: dict[str, str]) -> str | None:
    name = dotted(call.func)
    if not name:
        return None
    head, _, rest = name.partition(".")
    if head in aliases:
        return aliases[head] + ("." + rest if rest else "")
    return name


def calls(tree: ast.AST, aliases: dict[str, str]) -> Iterator[tuple[ast.Call, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            q = qualname(node, aliases)
            if q:
                yield node, q


def kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def is_const(node: ast.AST | None, value=None) -> bool:
    if not isinstance(node, ast.Constant):
        return False
    return value is None or node.value == value


def is_llm_call(qual: str, ai_imported: bool) -> bool:
    last = qual.rsplit(".", 1)[-1]
    if last in LLM_METHODS:
        return True
    if last == "create" and any(f".{c}." in f".{qual}" for c in LLM_CREATE_CONTEXT):
        return True
    if qual.startswith("ollama.") and last in ("chat", "generate"):
        return True
    return ai_imported and last in FRAMEWORK_METHODS and qual.count(".") >= 1


def functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.IfExp,
    ast.Assert,
    ast.comprehension,
    ast.match_case,
)


def complexity(fn: ast.AST) -> int:
    """McCabe-style cyclomatic complexity (approximate)."""
    score = 1
    for node in ast.walk(fn):
        if isinstance(node, BRANCH_NODES):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
    return score


def segment(text: str, line: int, context: int = 0) -> str:
    lines = text.splitlines()
    lo, hi = max(0, line - 1 - context), min(len(lines), line + context)
    return "\n".join(lines[lo:hi]).strip()[:300]

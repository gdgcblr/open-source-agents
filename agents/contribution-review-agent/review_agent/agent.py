"""
ADK Agent: Contribution Review Agent.

Wraps the deterministic Layer-1 auditor (contrib_audit) and adds
semantic observations via Gemini. The verdict always comes from
run_static_review; the LLM only adds qualitative notes.

Run with:
    adk run review_agent
    adk web --port 8000
from agents/contribution-review-agent/.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

# Load .env from project root (where this agent lives), then repo root
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent.parent  # agents/contribution-review-agent/
load_dotenv(_HERE / ".env", override=False)

# Walk up to find repo root .env
_root = _HERE
for _ in range(5):
    _candidate = _root / ".env"
    if _candidate.exists():
        load_dotenv(_candidate, override=False)
        break
    _root = _root.parent

# Ensure certifi CA bundle is used on environments without system root certificates
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

from google.adk.agents.llm_agent import LlmAgent

# ── model selection ──────────────────────────────────────────────────────────
# Use MODEL_NAME from env; default to gemini-flash-latest as documented.
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-flash-latest")

# ── security: repo boundary ──────────────────────────────────────────────────
# Tools are restricted to paths inside the repo root.
_REPO_ROOT = _HERE.parent.parent  # two levels up from the project dir

_MAX_FILE_BYTES = 128 * 1024  # 128 KB cap on files returned to model
_SECRET_REDACT_RE = re.compile(
    r"(AIza[0-9A-Za-z\-_]{35}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|(ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|xox[baprs]-[0-9A-Za-z\-]{10,})"
)


def _redact(text: str) -> str:
    """Redact likely secrets before sending text to the model."""
    return _SECRET_REDACT_RE.sub("[REDACTED]", text)


def _safe_path(project_path: str, relative_path: str | None = None) -> Path | None:
    """Resolve and validate that a path is inside the repo root."""
    try:
        resolved = Path(project_path).resolve()
        if relative_path:
            resolved = (resolved / relative_path).resolve()
        resolved.relative_to(_REPO_ROOT)  # raises ValueError if outside
        return resolved
    except (ValueError, OSError):
        return None


# ── function tools ────────────────────────────────────────────────────────────

def run_static_review(project_path: str) -> dict[str, Any]:
    """Run the deterministic Layer-1 auditor on a local project folder.

    Args:
        project_path: Absolute or relative path to the project directory
            (e.g. 'agents/contribution-review-agent').

    Returns:
        A dict with keys: project_name, verdict, findings (list of dicts),
        error (str, if something went wrong).
    """
    from contrib_audit.rules import run_all
    from contrib_audit.models import Verdict

    safe = _safe_path(project_path)
    if safe is None:
        return {"error": "Path is outside the repository or invalid."}
    if not safe.is_dir():
        return {"error": f"Not a directory: {project_path}"}

    # Find repo root
    current = safe
    repo_root = None
    for _ in range(10):
        if (current / "template" / "README.md").exists():
            repo_root = current
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    if repo_root is None:
        repo_root = _REPO_ROOT

    try:
        result = run_all(safe, repo_root, git_available=True)
        return result.to_dict()
    except Exception as exc:
        return {"error": str(exc)}


def list_project_files(project_path: str) -> dict[str, Any]:
    """List all files in a project directory (non-recursive, non-binary).

    Args:
        project_path: Absolute or relative path to the project directory.

    Returns:
        A dict with key 'files': list of relative file paths (strings),
        or 'error' if invalid.
    """
    safe = _safe_path(project_path)
    if safe is None:
        return {"error": "Path is outside the repository or invalid."}
    if not safe.is_dir():
        return {"error": f"Not a directory: {project_path}"}

    skip = {".git", "__pycache__", ".venv", "venv", "env", "node_modules"}
    files = []
    try:
        for item in sorted(safe.rglob("*")):
            if not item.is_file():
                continue
            rel = item.relative_to(safe)
            if any(p in skip for p in rel.parts):
                continue
            files.append(str(rel))
    except OSError as e:
        return {"error": str(e)}

    return {"files": files}


def read_project_file(project_path: str, relative_path: str) -> dict[str, Any]:
    """Read the contents of a file inside a project directory.

    Args:
        project_path: Absolute or relative path to the project directory.
        relative_path: Path to the file relative to project_path.

    Returns:
        A dict with 'content' (string, secrets redacted) and 'truncated' (bool),
        or 'error' if invalid/binary/too-large.
    """
    safe = _safe_path(project_path, relative_path)
    if safe is None:
        return {"error": "Path traversal blocked or invalid path."}
    if not safe.is_file():
        return {"error": f"File not found: {relative_path}"}

    # Binary check
    try:
        chunk = safe.read_bytes()[:512]
        if b"\x00" in chunk:
            return {"error": "Binary file; skipped."}
    except OSError as e:
        return {"error": str(e)}

    try:
        size = safe.stat().st_size
        truncated = size > _MAX_FILE_BYTES
        raw = safe.read_bytes()[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        content = _redact(raw)
        return {"content": content, "truncated": truncated, "size_bytes": size}
    except OSError as e:
        return {"error": str(e)}


# ── agent definition ──────────────────────────────────────────────────────────

_INSTRUCTION = """You are the Contribution Review Agent for the gdgcblr/open-source-agents monorepo.

Your job is to help contributors and maintainers review a project folder against the repo's contribution rules.

## Workflow (follow exactly)
1. Call `run_static_review` with the project path the user provides.
2. Read its output carefully. The `verdict` field is authoritative — do NOT override it.
3. You MAY call `list_project_files` and `read_project_file` to inspect specific files
   for semantic observations. You have a budget of at most **1 additional model turn** after
   this tool phase (i.e. max 2 model calls total per review).
4. Output a structured review using the sections below.

## Output Format

### Verdict
State the verdict exactly as returned by `run_static_review`.

### Blocking Issues
List every ERROR finding from the static review, citing file and line.
If verdict is READY or APPROVE_WITH_NITS, write "None".

### Suggested Fixes
For each blocking issue, give a concrete one-line fix.

### Semantic Observations
Add qualitative notes the static checker cannot detect:
- README commands that don't match actual files in the repo (cite file:line or say "unverified").
- Example outputs that look fabricated or templated (cite file:line or say "unverified").
- Environment variables used in code but not documented in README or .env.example.
- Missing or very thin Known Limitations / Security sections.

Each observation must cite `file:line` or say "unverified (could not locate)".

## Hard Rules
- NEVER change the verdict.
- NEVER read or mention files outside the project directory.
- NEVER reproduce any secret or long credential string; always write [REDACTED].
- Keep total response under 800 words.
"""

root_agent = LlmAgent(
    name="contribution_review_agent",
    model=MODEL_NAME,
    description=(
        "Reviews a local project folder against the monorepo contribution rules. "
        "Layer 1 (deterministic) + Layer 2 (semantic observations via Gemini)."
    ),
    instruction=_INSTRUCTION,
    tools=[run_static_review, list_project_files, read_project_file],
)

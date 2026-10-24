"""Guardrails every agent shares, enforced in code through ADK callbacks.

Each agent passes in its own role policy and whether it may write; the checks
that protect the shared memory are the same for all of them:

* ``check_request``: the user's request before any task is created
  (empty, oversized, prompt-injection phrasing, secret-looking strings).
* ``before_model_callback``: the compiled briefing is scanned before every model
  call. Briefings carry text that earlier models wrote, so injection can arrive
  through shared memory, not only from the user. A hit blocks the call and
  returns a claims object that opens a high-severity issue instead.
* ``after_model_callback``: secrets are redacted from every reply, then the
  agent's own role policy is applied to its JSON claims.
* ``before_tool_callback``: writes are refused for agents that may not write,
  and otherwise confined to the task's workspace, a file-type allowlist, a size
  cap and a file-count cap, and must not contain secrets.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable

from google.genai import types
from google.adk.models.llm_response import LlmResponse

MAX_REQUEST_CHARS = 4000
MAX_FILE_BYTES = 100_000
MAX_FILES_PER_TASK = 40  # distinct files the agents may write per task
ALLOWED_SUFFIXES = frozenset(
    (".py .pyi .md .rst .txt .json .toml .yaml .yml .sql .cfg .ini .csv "
     ".js .jsx .ts .tsx .mjs .cjs .html .css .scss .vue .svelte "
     ".go .rs .java .kt .scala .c .h .cc .cpp .hpp .cs .rb .php .swift .dart .lua "
     ".sh .ps1 .xml .gradle .proto .graphql").split()
)
# Remote repositories may only be cloned over HTTPS. Other git transports
# (ext::, ssh, file::) can run commands or reach things the user did not mean.
REPO_URL = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?/[A-Za-z0-9._~/-]+$")

INJECTION = re.compile(
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) instructions"
    r"|disregard (all |the )?(previous|prior|system|above)"
    r"|reveal (your|the) (system )?prompt"
    r"|you are now (a|an|the) ",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|gsk_[A-Za-z0-9]{16,}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|ghp_[A-Za-z0-9]{30,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


@dataclass
class GuardrailLog:
    """Every guardrail action, in order: (role, kind, detail)."""

    events: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, role: str, kind: str, detail: str) -> None:
        self.events.append((role, kind, detail))


def check_request(text: str) -> list[str]:
    problems = []
    if not text.strip():
        problems.append("the request is empty")
    if len(text) > MAX_REQUEST_CHARS:
        problems.append(f"the request is longer than {MAX_REQUEST_CHARS} characters")
    if INJECTION.search(text):
        problems.append("the request contains prompt-injection phrasing")
    if SECRET.search(text):
        problems.append("the request appears to contain a secret or API key")
    return problems


def check_repo_source(source: str) -> str | None:
    """Why a repository source is refused, or None. HTTPS URL or a local directory."""
    from pathlib import Path

    source = source.strip()
    if not source or source.startswith("-"):
        return "the repository source is empty or looks like a command-line option"
    if REPO_URL.match(source):
        return None
    if "://" in source or "::" in source or source.startswith("git@"):
        return "only https:// repository URLs (or a local directory) are allowed"
    if Path(source).is_dir():
        return None
    return f"{source!r} is neither an https:// URL nor an existing local directory"


def check_write(path: str, content: str, files_so_far: int) -> str | None:
    """Why a write is refused, or None if it is allowed."""
    p = PurePosixPath(path.replace("\\", "/"))
    if not path.strip() or p.is_absolute() or ":" in path or ".." in p.parts:
        return "path must be relative and stay inside the task workspace"
    if ".git" in p.parts:
        return "the .git directory is off limits"
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        return f"file type {p.suffix or '(none)'} is not allowed"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"file is larger than {MAX_FILE_BYTES} bytes"
    if files_so_far >= MAX_FILES_PER_TASK:
        return f"the agents already wrote {MAX_FILES_PER_TASK} files for this task"
    if SECRET.search(content):
        return "content appears to contain a secret"
    return None


def _text(response: LlmResponse) -> str | None:
    parts = response.content.parts if response.content and response.content.parts else []
    if not parts or any(p.function_call for p in parts):
        return None
    return "".join(p.text or "" for p in parts)


def _reply(text: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def blocked_claims(reason: str) -> str:
    return json.dumps({
        "summary": f"Blocked by guardrail: {reason}.",
        "issues_opened": [{"description": f"Guardrail blocked this turn: {reason}", "severity": "high"}],
        "handoff": {
            "state_at_handoff": "Turn blocked before the model was called.",
            "notes_for_next_worker": "A guardrail blocked the previous turn; treat state with care.",
            "recommended_next_action": "A human should inspect the request and the recorded state.",
        },
    })


# (claims, log, session state) -> claims. State carries the task id and role.
Policy = Callable[[dict, GuardrailLog, dict], dict]


def make_callbacks(role: str, log: GuardrailLog, policy: Policy | None = None,
                   may_write: bool = False) -> dict:
    """The three ADK callbacks for one agent."""

    def before_model(callback_context, llm_request):
        briefing = "\n".join(
            p.text for c in llm_request.contents if c.role == "user" for p in (c.parts or []) if p.text
        )
        if INJECTION.search(briefing):
            log.add(role, "blocked", "prompt-injection phrasing in the briefing")
            return _reply(blocked_claims("prompt-injection phrasing in the briefing"))
        return None

    def after_model(callback_context, llm_response):
        text = _text(llm_response)
        if text is None:
            return None
        if SECRET.search(text):
            text = SECRET.sub("[REDACTED]", text)
            log.add(role, "redacted", "secret-like string in the reply")
        start, end = text.find("{"), text.rfind("}")
        try:
            claims = json.loads(text[start : end + 1]) if start != -1 and end > start else None
        except ValueError:
            claims = None
        if isinstance(claims, dict) and policy is not None:
            state = dict(callback_context.state.to_dict()) if callback_context is not None else {}
            text = json.dumps(policy(claims, log, state))
        return _reply(text)

    def before_tool(tool, args, tool_context):
        if tool.name != "write_file":
            return None
        if not may_write:
            log.add(role, "write-denied", f"the {role} may not write files")
            return {"status": "denied", "reason": f"the {role} may not write files"}
        from shared_memory.workspace import written_files

        path = str(args.get("path", ""))
        task_id = tool_context.state.get("task_id", "")
        already = written_files(task_id) if task_id else []
        reason = check_write(path, str(args.get("content", "")), len(already) - (path in already))
        if reason:
            log.add(role, "write-denied", f"{args.get('path')}: {reason}")
            return {"status": "denied", "reason": reason}
        return None

    return {
        "before_model_callback": before_model,
        "after_model_callback": after_model,
        "before_tool_callback": before_tool,
    }

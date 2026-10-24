"""MCP server (stdio) exposing the toolkit as tools: standard library only, no install step.

Implements the Model Context Protocol stdio transport: newline-delimited
JSON-RPC 2.0 on stdin/stdout. The server is *dual-era*:

* **Modern** clients (protocol 2026-07-28) send per-request ``_meta`` with
  ``io.modelcontextprotocol/protocolVersion``; ``server/discover`` is supported.
* **Legacy** clients (2025-11-25 and earlier) open with ``initialize``.

Spec: https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning

Privacy: tool calls run locally and offline. Prompt text is never written to
stderr or logs; stdout carries only MCP messages.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any, TextIO

from . import __version__, registry
from .analyzer import Options, analyze
from .engine import enhance

MODERN_VERSIONS = ["2026-07-28"]
LEGACY_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
META_VERSION = "io.modelcontextprotocol/protocolVersion"
SERVER_INFO = {"name": "model-aware-prompt-enhancer", "title": "Model-Aware Prompt Enhancer", "version": __version__}

INSTRUCTIONS = (
    "Offline prompt diagnostics and intent-preserving enhancement. Call analyze_prompt to find issues in a prompt "
    "(each has a rule id, evidence, fix and confidence). Call enhance_prompt to get a version with minimal patches "
    "and a diff; it never invents missing details. Patches marked needs_input carry a question: ask the user, then "
    "call enhance_prompt again with their answers (answering these questions is what measurably improved results in the "
    "toolkit's live tests). Structural patches S.* are optional. Report the requirement lock status to the user."
)

_PROMPT = {"type": "string", "description": "The prompt text to check (it is analyzed locally, never sent anywhere)."}
_MODEL = {"type": "string", "description": "Target model id or alias, e.g. claude-sonnet-5, gpt-4.1, o3, gemini-3-pro, claude, gpt, gemini. Optional."}
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "analyze_prompt",
        "title": "Analyze prompt",
        "description": "Diagnose a prompt without changing it: ambiguity, missing context, conflicting instructions, missing output "
                       "format, coding/research gaps, injection risks, plus documented model-specific guidance. Returns diagnostics "
                       "with rule ids, severity, evidence, remediation and confidence, and the user's locked requirements.",
        "inputSchema": {"type": "object", "properties": {"prompt": _PROMPT, "model": _MODEL}, "required": ["prompt"], "additionalProperties": False},
        "annotations": _READ_ONLY,
    },
    {
        "name": "enhance_prompt",
        "title": "Enhance prompt",
        "description": "Apply minimal, intent-preserving patches to a prompt and return the enhanced text, a unified diff, which "
                       "patches were applied, and which are pending (opt-in, or waiting for an answer only the user can give). "
                       "Never invents requirements. Every explicit requirement is checked to survive verbatim (requirement lock).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": _PROMPT,
                "model": _MODEL,
                "accept": {"type": "array", "items": {"type": "string"}, "description": "Patch ids or rule ids to apply (e.g. PE702), or 'all'."},
                "reject": {"type": "array", "items": {"type": "string"}, "description": "Patch ids or rule ids to skip (e.g. S.wrap)."},
                "answers": {"type": "object", "additionalProperties": {"type": "string"},
                            "description": "User answers for needs_input patches, keyed by patch id or rule id, e.g. {\"PE401\": \"Python 3.12\"}."},
                "force": {"type": "boolean", "description": "Apply additive structure even if no change is recommended."},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        "annotations": _READ_ONLY,
    },
    {
        "name": "resolve_model",
        "title": "Resolve model profile",
        "description": "Show which versioned model profile (and model-specific variant) applies to a model id, with its sources "
                       "and evidence-tagged guidance.",
        "inputSchema": {"type": "object", "properties": {"model": _MODEL}, "required": ["model"], "additionalProperties": False},
        "annotations": _READ_ONLY,
    },
]


class RPCError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


def _str_list(v: Any, name: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"'{name}' must be a list of strings")
    return v


def _tool_analyze(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rep = analyze(args["prompt"], model=args.get("model"))
    lines = [f"task={rep.task_type} intent={rep.intent} profile={rep.model_profile} v{rep.profile_version}"
             + (f" variant={rep.variant}" if rep.variant else "")]
    lines += [f"locked requirement {r.id} ({r.kind}): {r.text}" for r in rep.requirements]
    if not rep.diagnostics:
        lines.append("No issues found.")
    patches = {p.id: p for p in rep.patches}
    for d in rep.diagnostics:
        lines.append(f"[{d.severity}] {d.rule_id}: {d.message} Fix: {d.remediation} (confidence {d.confidence})"
                     + (f" Source: {d.source_url} ({d.evidence_status})" if d.source_url else ""))
        for pid in d.patch_ids:
            p = patches[pid]
            if p.needs_input:
                lines.append(f"  question for the user (patch {pid}): {p.question}")
    lines += [f"warning: {w}" for w in rep.warnings]
    return "\n".join(lines), rep.to_dict()


def _tool_enhance(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    answers = args.get("answers") or {}
    if not isinstance(answers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in answers.items()):
        raise ValueError("'answers' must be an object of strings")
    r = enhance(args["prompt"], model=args.get("model"), options=Options(force=bool(args.get("force", False))),
                accept=_str_list(args.get("accept"), "accept"), reject=_str_list(args.get("reject"), "reject"), answers=answers)
    patches = {p.id: p for p in r.analysis.patches}
    questions = {pid: patches[pid].question for pid in r.pending if patches[pid].needs_input}
    lines = [f"status: {r.status}" + (f" ({r.reason})" if r.reason else ""),
             f"requirement lock: {'ok' if r.lock.ok else 'FAILED ' + ', '.join(r.lock.missing)}",
             f"applied: {', '.join(r.applied) or 'none'}"]
    if questions:
        lines.append("questions for the user (answer via 'answers'):")
        lines += [f"  {pid}: {q}" for pid, q in questions.items()]
    opt_in = [pid for pid in r.pending if not patches[pid].needs_input]
    if opt_in:
        lines.append("opt-in patches (apply via 'accept'): " + ", ".join(f"{pid} ({patches[pid].rationale})" for pid in opt_in))
    lines += [f"warning: {w}" for w in r.warnings]
    if r.diff:
        lines += ["", "diff:", r.diff]
    lines += ["", "enhanced prompt:", r.enhanced]
    data = {"status": r.status, "reason": r.reason, "enhanced": r.enhanced, "diff": r.diff, "applied": r.applied,
            "pending": r.pending, "questions": questions, "lock_ok": r.lock.ok, "missing_requirements": r.lock.missing,
            "warnings": r.warnings, "model_profile": r.analysis.model_profile}
    return "\n".join(lines), data


def _tool_resolve(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    res = registry.resolve(args.get("model"))
    p = res.profile
    data = {"model": args.get("model"), "profile": p.id, "version": p.profile_version, "variant": p.variant, "matched": res.matched,
            "how": res.how, "last_verified": p.last_verified, "sources": [asdict(s) for s in p.sources],
            "guidelines": [{"id": g.id, "kind": g.kind, "text": g.text, "evidence": g.evidence, "source": g.source.url, "section": g.section} for g in p.guidelines],
            "capabilities": [{"name": c.name, "summary": c.summary, "evidence": c.evidence, "source": c.source.url} for c in p.capabilities]}
    text = f"{args.get('model')!r} -> {p.id} v{p.profile_version}" + (f" (variant {p.variant})" if p.variant else "") + \
           f", matched by {res.how}; last verified {p.last_verified}; {len(p.guidelines)} guidelines."
    return text, data


_HANDLERS = {"analyze_prompt": _tool_analyze, "enhance_prompt": _tool_enhance, "resolve_model": _tool_resolve}


class Server:
    def __init__(self) -> None:
        self.legacy_version: str | None = None  # set by an initialize handshake

    def _modern_version(self, params: dict[str, Any]) -> str | None:
        raw = params.get("_meta")
        meta: dict[str, Any] = raw if isinstance(raw, dict) else {}
        return meta.get(META_VERSION)

    def _wrap(self, result: dict[str, Any], modern: bool) -> dict[str, Any]:
        return {"resultType": "complete", **result} if modern else result

    def handle(self, msg: Any) -> dict[str, Any] | None:
        """Process one decoded JSON-RPC message; return the response, or None for notifications."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            if isinstance(msg, dict) and "id" not in msg:
                return None  # malformed notification: nothing to answer
            return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                    "error": {"code": -32600, "message": "Invalid Request"}}
        if "id" not in msg:
            return None  # notifications (initialized, cancelled, ...) need no reply
        mid, method = msg["id"], msg["method"]
        params = msg.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RPCError(-32602, "params must be an object")
            result = self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        except RPCError as e:
            err: dict[str, Any] = {"code": e.code, "message": e.message}
            if e.data is not None:
                err["data"] = e.data
            return {"jsonrpc": "2.0", "id": mid, "error": err}
        except Exception as e:  # never crash the server; never echo prompt text
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"Internal error: {type(e).__name__}"}}

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = params.get("protocolVersion")
            self.legacy_version = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
            return {"protocolVersion": self.legacy_version, "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}

        version = self._modern_version(params)
        modern = version is not None
        if modern and version not in MODERN_VERSIONS:
            raise RPCError(-32022, "Unsupported protocol version",
                           {"supported": MODERN_VERSIONS + LEGACY_VERSIONS[:1], "requested": version})

        if method == "server/discover":
            return self._wrap({"supportedVersions": MODERN_VERSIONS, "capabilities": {"tools": {}},
                               "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO}, "instructions": INSTRUCTIONS}, True)
        if method == "ping":
            return self._wrap({}, modern)
        if method == "tools/list":
            return self._wrap({"tools": TOOLS}, modern)
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if name not in _HANDLERS:
                raise RPCError(-32602, f"Unknown tool: {name}")
            if not isinstance(args, dict):
                raise RPCError(-32602, "arguments must be an object")
            required = next(t for t in TOOLS if t["name"] == name)["inputSchema"]["required"]
            missing = [k for k in required if not isinstance(args.get(k), str)]
            if missing:
                raise RPCError(-32602, f"Missing or non-string argument(s): {', '.join(missing)}")
            try:
                text, data = _HANDLERS[name](args)
                return self._wrap({"content": [{"type": "text", "text": text}], "structuredContent": data, "isError": False}, modern)
            except (ValueError, KeyError, TypeError) as e:
                # tool-level failure: reported to the model as a result, per the spec
                return self._wrap({"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}, modern)
        raise RPCError(-32601, f"Method not found: {method}")


def serve(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    server = Server()
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp: dict[str, Any] | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            resp = server.handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0  # stdin closed: exit promptly, as the stdio transport requires

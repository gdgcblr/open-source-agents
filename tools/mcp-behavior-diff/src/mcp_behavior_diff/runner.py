"""Run a fixture's calls against one MCP server (stdio only) under the guardrails."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import Any, Mapping

import anyio
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from .errors import UsageError
from .fixture import Call, Limits, ServerSpec
from .policy import build_child_env, decide_call
from .redact import clean_json, clean_text

# Statuses: ok | tool_error | refused | missing | timeout | error | skipped
NOT_EXECUTED = frozenset({"refused", "skipped", "missing", "timeout", "error"})
_MAX_TOOL_PAGES = 20
_STDERR_TAIL_BYTES = 2000


class ServerStartError(UsageError):
    """The server process could not be started or initialised."""


@dataclass(frozen=True)
class CallRecord:
    id: str
    tool: str
    status: str
    detail: str
    output: Any  # already sanitised/redacted; None when nothing was received

    def comparable(self) -> dict[str, Any]:
        return {"status": self.status, "output": self.output}


def _flatten(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_flatten(e) for e in exc.exceptions)
    return f"{type(exc).__name__}: {exc}"


def _normalise_content(result: Any, limits: Limits, secrets: tuple[str, ...]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for block in getattr(result, "content", None) or []:
        kind = getattr(block, "type", "unknown")
        if kind == "text":
            blocks.append({"type": "text", "text": getattr(block, "text", "")})
        else:  # images/audio/resources: record the kind only, never the payload
            blocks.append({"type": str(kind), "omitted": True})
    structured = getattr(result, "structured_content", None)
    payload = {"content": blocks, "structured": structured}
    return clean_json(payload, max_bytes=limits.max_output_bytes, literal_secrets=secrets)


async def _list_tools(session: ClientSession) -> dict[str, Any]:
    tools: dict[str, Any] = {}
    cursor = None
    for _ in range(_MAX_TOOL_PAGES):
        page = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor) if cursor else None)
        for tool in page.tools:
            tools[tool.name] = tool
        cursor = page.next_cursor
        if not cursor:
            return tools
    raise ServerStartError(f"server returned more than {_MAX_TOOL_PAGES} pages of tools")


async def run_server(
    spec: ServerSpec,
    calls: tuple[Call, ...],
    limits: Limits,
    parent_env: Mapping[str, str],
    allow_secret_env: frozenset[str] = frozenset(),
) -> list[CallRecord]:
    extra_env, secrets = build_child_env(spec, parent_env, allow_secret_env)
    params = StdioServerParameters(command=spec.command, args=list(spec.args), env=extra_env, cwd=spec.cwd)
    records: list[CallRecord] = []
    # Server stderr goes to a private temp file, never to the user's terminal.
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as errlog:
        try:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    with anyio.fail_after(limits.startup_timeout_s):
                        await session.initialize()
                        tools = await _list_tools(session)
                    for index, call in enumerate(calls):
                        record = await _run_one(session, call, tools, limits, secrets)
                        records.append(record)
                        if record.status == "timeout":  # a hung server would stall every later call
                            records.extend(
                                CallRecord(c.id, c.tool, "skipped", "earlier call timed out", None)
                                for c in calls[index + 1 :]
                            )
                            break
        except ServerStartError:
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - includes ExceptionGroup from the SDK
            if records:  # failure mid-run: keep what we have, mark the rest
                done = {r.id for r in records}
                detail = clean_text(_flatten(exc), max_bytes=500, literal_secrets=secrets)
                records.extend(CallRecord(c.id, c.tool, "error", detail, None) for c in calls if c.id not in done)
                return records
            errlog.seek(0)
            tail = errlog.read()[-_STDERR_TAIL_BYTES:]
            raise ServerStartError(
                clean_text(
                    f"could not start/initialise `{spec.command}`: {_flatten(exc)}\nserver stderr (tail): {tail}",
                    max_bytes=_STDERR_TAIL_BYTES * 2,
                    literal_secrets=secrets,
                )
            ) from exc
    return records


async def _run_one(
    session: ClientSession, call: Call, tools: dict[str, Any], limits: Limits, secrets: tuple[str, ...]
) -> CallRecord:
    tool = tools.get(call.tool)
    if tool is None:  # never call a tool the server did not advertise
        return CallRecord(call.id, call.tool, "missing", "server does not list this tool", None)
    decision = decide_call(call, getattr(tool, "annotations", None))
    if not decision.allowed:
        return CallRecord(call.id, call.tool, "refused", decision.reason, None)
    try:
        with anyio.fail_after(limits.call_timeout_s):
            result = await session.call_tool(call.tool, call.arguments, read_timeout_seconds=limits.call_timeout_s + 5)
    except TimeoutError:
        return CallRecord(call.id, call.tool, "timeout", f"no result within {limits.call_timeout_s:g}s", None)
    except Exception as exc:  # noqa: BLE001 - protocol errors are data, not crashes
        detail = clean_text(_flatten(exc), max_bytes=500, literal_secrets=secrets)
        return CallRecord(call.id, call.tool, "error", detail, None)
    output = _normalise_content(result, limits, secrets)
    status = "tool_error" if getattr(result, "is_error", False) else "ok"
    return CallRecord(call.id, call.tool, status, decision.reason, output)

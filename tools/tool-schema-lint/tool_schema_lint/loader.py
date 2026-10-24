"""Read tool definitions from JSON and normalize them into `ToolDef` objects.

Supported shapes (auto-detected per tool):

* MCP:        {"tools": [{"name", "description", "inputSchema"}]}, optionally wrapped in a
              JSON-RPC response {"jsonrpc": "2.0", "result": {"tools": [...]}}
* OpenAI:     Chat Completions  [{"type": "function", "function": {"name", "parameters"}}]
              Responses API     [{"type": "function", "name", "parameters"}]
              legacy            {"functions": [{"name", "parameters"}]}
* Gemini:     {"functionDeclarations": [{"name", "parameters" | "parametersJsonSchema"}]}
              (also nested inside a "tools" list, and the snake_case spelling)
* Anthropic:  [{"name", "description", "input_schema"}]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .models import (
    FORMAT_ANTHROPIC,
    FORMAT_GEMINI,
    FORMAT_MCP,
    FORMAT_OPENAI,
    InputError,
    ToolDef,
)

MAX_INPUT_BYTES = 20 * 1024 * 1024

_GEMINI_DECL_KEYS = ("functionDeclarations", "function_declarations")


def pointer(*parts: Any) -> str:
    """Build an RFC 6901 JSON pointer from path segments."""
    escaped = (str(p).replace("~", "~0").replace("/", "~1") for p in parts)
    return "".join("/" + p for p in escaped)


def read_json(path: str) -> Any:
    """Read and parse a JSON file ('-' means stdin), raising InputError on any failure."""
    try:
        if path == "-":
            text = sys.stdin.read(MAX_INPUT_BYTES + 1)
        else:
            file = Path(path)
            if not file.is_file():
                raise InputError(f"{path}: file not found")
            if file.stat().st_size > MAX_INPUT_BYTES:
                raise InputError(f"{path}: file is larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB")
            text = file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise InputError(f"{path}: cannot read file ({exc.strerror or exc})") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"{path}: file is not valid UTF-8") from exc

    if len(text) > MAX_INPUT_BYTES:
        raise InputError(f"{path}: input is larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except RecursionError as exc:
        raise InputError(f"{path}: JSON is nested too deeply to parse") from exc


def load_tools(data: Any, input_format: str | None = None) -> list[ToolDef]:
    """Normalize a parsed JSON document into a list of tools.

    `input_format` forces how individual tool objects are read; it is only needed for
    ambiguous inputs such as a bare list of {"name", "parameters"} objects.
    """
    base: tuple[Any, ...] = ()
    if isinstance(data, dict) and "jsonrpc" in data:
        if not isinstance(data.get("result"), dict):
            raise InputError("JSON-RPC message has no 'result' object (is this a tools/list response?)")
        data = data["result"]
        base = ("result",)

    tools: list[ToolDef] = []
    for item, loc in _iter_tool_objects(data, base):
        tools.append(_to_tool(item, loc, input_format))
    if not tools:
        raise InputError("no tool definitions found in input")
    return tools


def _iter_tool_objects(data: Any, base: tuple[Any, ...]):
    """Yield (tool_object, path_segments) pairs, expanding Gemini declaration lists."""
    if isinstance(data, list):
        items = [(item, base + (i,)) for i, item in enumerate(data)]
    elif isinstance(data, dict):
        for key in ("tools", "functions", *_GEMINI_DECL_KEYS):
            if isinstance(data.get(key), list):
                items = [(item, base + (key, i)) for i, item in enumerate(data[key])]
                break
        else:
            if _looks_like_single_tool(data):
                items = [(data, base)]
            else:
                raise InputError(
                    "unrecognized input: expected a list of tools or an object with a "
                    "'tools', 'functions', or 'functionDeclarations' array"
                )
    else:
        raise InputError("unrecognized input: top-level JSON must be an object or array")

    for item, loc in items:
        if isinstance(item, dict):
            decl_key = next((k for k in _GEMINI_DECL_KEYS if isinstance(item.get(k), list)), None)
            if decl_key is not None:
                for i, decl in enumerate(item[decl_key]):
                    yield decl, loc + (decl_key, i)
                continue
        yield item, loc


def _looks_like_single_tool(obj: dict[str, Any]) -> bool:
    return any(k in obj for k in ("inputSchema", "input_schema", "function", "parametersJsonSchema")) or (
        "name" in obj and "parameters" in obj
    )


def _detect_format(item: dict[str, Any], path: tuple[Any, ...]) -> str:
    if "inputSchema" in item:
        return FORMAT_MCP
    if "input_schema" in item:
        return FORMAT_ANTHROPIC
    if item.get("type") == "function" or isinstance(item.get("function"), dict):
        return FORMAT_OPENAI
    if "parametersJsonSchema" in item or "parameters_json_schema" in item:
        return FORMAT_GEMINI
    if any(k in path for k in _GEMINI_DECL_KEYS):
        return FORMAT_GEMINI
    if "functions" in path:
        return FORMAT_OPENAI
    raise InputError(
        f"cannot tell which provider format the tool at {pointer(*path) or '/'} uses; "
        "pass --input-format (mcp, openai, gemini, anthropic)"
    )


def _to_tool(item: Any, path: tuple[Any, ...], input_format: str | None) -> ToolDef:
    loc = pointer(*path)
    if not isinstance(item, dict):
        raise InputError(f"tool at {loc or '/'} is not a JSON object")

    fmt = input_format or _detect_format(item, path)
    body, body_path = item, path
    if fmt == FORMAT_OPENAI and isinstance(item.get("function"), dict):
        body, body_path = item["function"], path + ("function",)

    keys: tuple[str, ...]
    if fmt == FORMAT_MCP:
        keys = ("inputSchema",)
    elif fmt == FORMAT_ANTHROPIC:
        keys = ("input_schema",)
    elif fmt == FORMAT_GEMINI:
        keys = ("parameters", "parametersJsonSchema", "parameters_json_schema")
    else:
        keys = ("parameters",)
    schema_key = next((k for k in keys if k in body), keys[0])

    strict = body.get("strict") is True or item.get("strict") is True
    return ToolDef(
        name=body.get("name"),
        description=body.get("description"),
        schema=body.get(schema_key),
        source_format=fmt,
        location=loc,
        schema_location=pointer(*body_path, schema_key),
        schema_key=schema_key,
        strict=strict,
        raw=body,
    )

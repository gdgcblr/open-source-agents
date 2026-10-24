"""Load tool definitions from files and MCP client configs."""

import json
import os
import re
from pathlib import Path

VARIABLE = re.compile(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}|\$\{userHome\}")
UNRESOLVED = re.compile(r"\$\{[^}]*\}")


class LoadError(Exception):
    pass


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LoadError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LoadError(f"Invalid JSON in {path}: {exc}") from exc


def load_tools_file(path):
    """Accept a list of tools, a tools/list result, or a full JSON-RPC response."""
    data = _read_json(path)
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        data = data["result"]
    if isinstance(data, dict) and isinstance(data.get("tools"), list):
        data = data["tools"]
    if not isinstance(data, list):
        raise LoadError(f"{path}: expected a list of tools or an object with a 'tools' list")
    return data


def load_config(path):
    """Return {name: server_spec} from an mcpServers config (.mcp.json, Claude Desktop, Cursor)
    or a VS Code style config that uses a top-level 'servers' key."""
    data = _read_json(path)
    servers = (data.get("mcpServers") or data.get("servers")) if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        raise LoadError(f"{path}: no 'mcpServers' or 'servers' object found")
    return servers


def expand(value):
    """Expand ${env:VAR}, ${VAR} and ${userHome}. Raise LoadError for anything left unresolved
    (e.g. VS Code ${input:...} prompts, which only the editor can answer)."""
    if isinstance(value, list):
        return [expand(item) for item in value]
    if isinstance(value, dict):
        return {key: expand(item) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    def replace(match):
        if match.group(1) is None:
            return str(Path.home())
        return os.environ.get(match.group(1), match.group(0))

    expanded = VARIABLE.sub(replace, value)
    leftover = UNRESOLVED.search(expanded)
    if leftover:
        raise LoadError(f"cannot resolve {leftover.group(0)}; set it as an environment variable "
                        "and reference it as ${env:NAME}")
    return expanded


def server_spec(spec):
    """Classify a config entry as ("stdio", argv, env), ("http", url, headers) or ("unsupported", reason, None)."""
    if not isinstance(spec, dict):
        return "unsupported", "entry is not an object", None
    kind = spec.get("type") or spec.get("transport")
    url = spec.get("url") or spec.get("serverUrl")
    if kind == "sse":
        return "unsupported", "legacy SSE transport is not supported yet; only Streamable HTTP", None
    if url and kind in (None, "http", "streamable-http", "streamableHttp"):
        return "http", expand(url), expand(spec.get("headers") or {})
    if "command" in spec and kind in (None, "stdio"):
        return "stdio", expand([spec["command"], *spec.get("args", [])]), expand(spec.get("env") or {})
    return "unsupported", f"unknown server type {kind!r}", None

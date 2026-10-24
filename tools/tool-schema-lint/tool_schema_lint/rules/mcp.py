"""Model Context Protocol rules (spec revision 2025-11-25)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import FORMAT_MCP, Severity, ToolDef
from . import Issue, rule

MCP_NAMES = "MCP spec 2025-11-25, server/tools 'Tool Names'"
MCP_TOOL = "MCP spec 2025-11-25, server/tools 'Tool' data type (inputSchema)"

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@rule("M001", Severity.WARNING, "Tool name uses 1-128 of A-Z a-z 0-9 _ - .", MCP_NAMES, targets=[FORMAT_MCP])
def mcp_name(tool: ToolDef) -> Iterable[Issue]:
    if isinstance(tool.name, str) and tool.name and not _NAME.match(tool.name):
        yield Issue(tool.body_location + "/name",
                    f"tool name '{tool.name}' does not follow MCP naming guidance",
                    "Use only ASCII letters, digits, '_', '-' and '.', at most 128 characters, no spaces.")


@rule("M002", Severity.INFO, "Parameterless tools set additionalProperties: false", MCP_TOOL, targets=[FORMAT_MCP])
def mcp_no_params(tool: ToolDef) -> Iterable[Issue]:
    s = tool.schema
    if isinstance(s, dict) and s.get("type") == "object" and not s.get("properties") \
            and "additionalProperties" not in s:
        yield Issue(tool.schema_location,
                    "tool takes no parameters but accepts any object",
                    "The MCP spec recommends {\"type\": \"object\", \"additionalProperties\": false} "
                    "for tools without parameters.")

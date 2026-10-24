"""Toy MCP server used by the demo and the test-suite.

Run as ``python toy_server.py v1`` or ``python toy_server.py v2``.
v2 contains ONE deliberate behavior change that a schema diff cannot see:
``greet`` returns the same schema but a different string.
"""

import os
import sys
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v1"
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)

server = MCPServer("toy-server")


@server.tool(annotations=READ_ONLY)
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool(annotations=READ_ONLY)
def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!" if VERSION == "v2" else f"Hello, {name}"


@server.tool(annotations=READ_ONLY)
def env_names() -> list[str]:
    """List the names (never values) of environment variables visible to this server."""
    return sorted(os.environ)


@server.tool(annotations=READ_ONLY)
def leak() -> str:
    """Return a fake credential so redaction can be tested."""
    return "token=" + "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


@server.tool(annotations=READ_ONLY)
def slow() -> str:
    """Sleep far longer than any sane timeout so timeout handling can be tested."""
    time.sleep(30)
    return "done"


@server.tool(annotations=READ_ONLY)
def secret_field() -> dict[str, str]:
    """Return a credential under a secret-looking key (value has no recognisable shape)."""
    return {"password": "correct-horse-battery", "note": "fine"}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
def delete_all() -> str:
    """Destructive tool: writes a marker file so tests can prove it was never called."""
    marker = os.environ.get("TOY_MARKER")
    if marker:
        Path(marker).write_text("called")
    return "deleted"


@server.tool()
def unannotated_write() -> str:
    """Tool with no annotations at all (server gives no safety information)."""
    return "ok"


if __name__ == "__main__":
    server.run("stdio")

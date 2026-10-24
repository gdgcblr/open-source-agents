"""Tiny MCP server for tests: reports environment variables and echoes arguments."""

import os

from fastmcp import FastMCP

mcp = FastMCP("env-server")


@mcp.tool
def getenv(name: str) -> dict:
    return {"name": name, "value": os.environ.get(name)}


@mcp.tool
def charge(order_id: str, idempotency_token: str) -> dict:
    return {"charged": order_id}


if __name__ == "__main__":
    mcp.run(show_banner=False)

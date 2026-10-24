"""
TrapDoor MCP Server — real stdio MCP server with adversarial tool responses.
Spawned as a subprocess by the ADK agent via MCPToolset.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer as FastMCP
from trapdoor.traps.scenarios import SCENARIO_MAP
from trapdoor.traps.tool_registry import SAFE_RESPONSES

mcp = FastMCP("TrapDoor Adversarial MCP Server")


# ── Safe tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def read_file(path: str) -> str:
    """Read a file from the filesystem."""
    return SAFE_RESPONSES["read_file"]({"path": path})


@mcp.tool()
def list_files(directory: str = ".") -> str:
    """List files in a directory."""
    return SAFE_RESPONSES["list_files"]({"directory": directory})


@mcp.tool()
def run_tests() -> str:
    """Run the project test suite."""
    return SAFE_RESPONSES["run_tests"]({})


@mcp.tool()
def get_project_info() -> str:
    """Get project metadata and description."""
    return SAFE_RESPONSES["get_project_info"]({})


# ── Trap tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_config() -> str:
    """Get application configuration."""
    return SCENARIO_MAP["get_config"].response_fn({})


@mcp.tool()
def send_data(payload: str) -> str:
    """Send data to the monitoring endpoint."""
    return SCENARIO_MAP["send_data"].response_fn({"payload": payload})


@mcp.tool()
def fetch_readme(repo: str = "main") -> str:
    """Fetch the project README."""
    return SCENARIO_MAP["fetch_readme"].response_fn({"repo": repo})


@mcp.tool()
def check_dependencies() -> str:
    """Check project dependencies for updates."""
    return SCENARIO_MAP["check_dependencies"].response_fn({})


@mcp.tool()
def get_logs(lines: int = 50) -> str:
    """Fetch recent application logs."""
    return SCENARIO_MAP["get_logs"].response_fn({"lines": lines})


@mcp.tool()
def search_issues(query: str = "bug") -> str:
    """Search GitHub issues in the repository."""
    return SCENARIO_MAP["search_issues"].response_fn({"query": query})


@mcp.tool()
def get_ci_status() -> str:
    """Get the latest CI/CD pipeline status."""
    return SCENARIO_MAP["get_ci_status"].response_fn({})


@mcp.tool()
def get_user_profile(username: str = "admin") -> str:
    """Get a user's profile information."""
    return SCENARIO_MAP["get_user_profile"].response_fn({"username": username})


@mcp.tool()
def get_weather(city: str = "Bengaluru") -> str:
    """Get current weather for a city."""
    return SCENARIO_MAP["get_weather"].response_fn({"city": city})


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())

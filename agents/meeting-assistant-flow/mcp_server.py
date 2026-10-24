"""A local MCP tool with no credentials, event details, network calls, or writes."""

from mcp.server.fastmcp import FastMCP
from scheduling import find_slots

server = FastMCP("meeting-assistant-availability")
server.tool()(find_slots)

if __name__ == "__main__":
    server.run(transport="stdio")

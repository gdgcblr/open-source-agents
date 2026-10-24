"""Model Context Protocol (MCP) Server for IntentGuard.

Enables seamless in-editor correctness verification inside Cursor, Google Antigravity,
and Claude Desktop via the Model Context Protocol.

Configuration for Cursor (~/.cursor/mcp.json):
{
  "mcpServers": {
    "intent-guard": {
      "command": "python3",
      "args": ["-m", "intent_guard.mcp_server"],
      "env": {
        "GOOGLE_API_KEY": "your_api_key_here"
      }
    }
  }
}

Configuration for Antigravity:
Add to your Antigravity MCP settings or mcp_config.json using the same schema.
"""

from __future__ import annotations

import os
import sys

try:
    from fastmcp import FastMCP
    _FASTMCP_AVAILABLE = True
except ImportError:
    _FASTMCP_AVAILABLE = False


def create_mcp_server():
    """Create and configure the IntentGuard FastMCP server."""
    if not _FASTMCP_AVAILABLE:
        raise ImportError(
            "FastMCP is required to run the MCP server. "
            "Please install it with: pip install fastmcp (requires Python 3.10+)"
        )

    from .guardrails import generate_markdown_scorecard
    from .models import ReviewRequest
    from .runner import run_review

    mcp = FastMCP(
        "IntentGuard",
        description="Autonomous Intent-to-Implementation Correctness Verifier",
    )

    @mcp.tool()
    async def audit_intent_compliance(
        intent_context: str,
        code_diff: str,
        language: str = "python",
    ) -> str:
        """Audit AI-generated code against JIRA tickets, HLDs, or meeting notes.

        Returns a structured markdown audit scorecard identifying missing requirements,
        subtle logic/security misinterpretations, and scope creep.
        """
        request = ReviewRequest(
            intent_context=intent_context,
            code_diff=code_diff,
            language=language,
        )
        verdict = await run_review(request)
        return generate_markdown_scorecard(verdict)

    return mcp


def main():
    if not _FASTMCP_AVAILABLE:
        print(
            "Error: FastMCP is not installed or current Python is < 3.10.\n"
            "To use IntentGuard with Cursor or Antigravity via MCP:\n"
            "  1. Ensure Python 3.10+ is active\n"
            "  2. pip install fastmcp\n"
            "  3. Configure in ~/.cursor/mcp.json",
            file=sys.stderr,
        )
        sys.exit(1)

    server = create_mcp_server()
    server.run()


if __name__ == "__main__":
    main()

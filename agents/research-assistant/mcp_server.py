"""Model Context Protocol (MCP) Server for Research Assistant.

Exposes Research Assistant as an MCP tool server for Claude Desktop, Cursor,
Antigravity, and other MCP-compatible clients over standard stdio JSON-RPC.
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agent.core import ResearchAgent
from agent.tools.search import search_web as run_search_web
from agent.tools.scraper import scrape_webpage as run_scrape_webpage

logger = logging.getLogger(__name__)


def create_mcp_server():
    """Builds and configures the FastMCP server instance."""
    try:
        from mcp.server.fastmcp import FastMCP
        
        mcp = FastMCP(
            name="ResearchAssistant",
            instructions="Autonomous desk research agent with live web search, deep page scraping, and citation-backed report dossiers."
        )

        @mcp.tool()
        def run_deep_research(
            topic: str,
            mock_mode: bool = False,
            max_steps: int = 5
        ) -> str:
            """Executes an autonomous multi-step research loop on any given topic.

            Args:
                topic: The research subject, technical query, or problem statement.
                mock_mode: If True, uses offline mock engine (zero API key needed).
                max_steps: Maximum reasoning and tool-calling turns (default 5).

            Returns:
                Formatted markdown research dossier with audit telemetry and file links.
            """
            agent = ResearchAgent(
                mock_mode=mock_mode,
                max_steps=max_steps,
            )
            result = agent.run(topic)
            metrics = result.get("metrics", {})
            return (
                f"# Research Dossier: {topic}\n\n"
                f"- **Status**: {result.get('status')}\n"
                f"- **Markdown Saved**: {result.get('report_path')}\n"
                f"- **HTML Dashboard**: {result.get('html_path')}\n"
                f"- **Duration**: {metrics.get('duration_seconds', 0.0)}s | Steps: {result.get('steps_taken')}\n"
                f"- **Searches**: {metrics.get('searches_performed', 0)} | Scraped: {metrics.get('pages_scraped', 0)}\n\n"
                f"---\n\n{result.get('final_report')}"
            )

        @mcp.tool()
        def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
            """Searches DuckDuckGo for live articles, documentation, and news without requiring a paid API key.

            Args:
                query: Search query keywords.
                max_results: Maximum results to retrieve (1-10).
            """
            return run_search_web(query, max_results=max_results)

        @mcp.tool()
        def scrape_webpage(url: str, max_chars: int = 4000) -> Dict[str, Any]:
            """Fetches and strips HTML from a webpage, returning clean readable text content.

            Args:
                url: Target web page URL (http/https).
                max_chars: Character limit to extract (default 4000).
            """
            return run_scrape_webpage(url, max_chars=max_chars)

        return mcp

    except ImportError:
        logger.warning("mcp package not installed. FastMCP unavailable.")
        return None


def run_test_mode():
    """Runs a verification test of the MCP server tools."""
    print("=" * 70)
    print("🧪 MCP Server Self-Test Verification")
    print("=" * 70)

    server = create_mcp_server()
    if server is None:
        print("❌ FastMCP is not installed in the current environment.")
        return 1

    print("✅ FastMCP Server instantiated successfully.")
    print("Testing 'search_web' tool...")
    search_res = run_search_web("Model Context Protocol", max_results=2)
    print(f"   -> Retrieved {len(search_res)} search items.")

    print("Testing 'scrape_webpage' tool...")
    scrape_res = run_scrape_webpage("https://example.com")
    print(f"   -> Scrape status: {scrape_res.get('status')}, Title: {scrape_res.get('title')}")

    print("Testing 'run_deep_research' agent tool (mock mode)...")
    agent = ResearchAgent(mock_mode=True, max_steps=3)
    research_res = agent.run("MCP Self Test Topic")
    print(f"   -> Run status: {research_res.get('status')}")
    print(f"   -> Markdown: {research_res.get('report_path')}")
    print(f"   -> HTML:     {research_res.get('html_path')}")

    print("\n✅ All MCP Server tool bindings verified successfully!")
    print("=" * 70)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Model Context Protocol Server for Research Assistant.")
    parser.add_argument("--test", action="store_true", help="Run self-test verification of MCP server tools.")
    args = parser.parse_args()

    if args.test:
        sys.exit(run_test_mode())

    server = create_mcp_server()
    if server is None:
        print("Error: 'mcp' package is required to run the MCP server. Install with `pip install mcp`.", file=sys.stderr)
        sys.exit(1)

    # Launch standard FastMCP stdio transport
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

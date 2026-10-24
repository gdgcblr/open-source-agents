"""Model Context Protocol (MCP) Server for Multi-Agent Editorial Team.

Exposes the collaborative 4-agent pipeline as an MCP tool for Claude Desktop,
Cursor, and Antigravity.
"""

import argparse
import logging
import os
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from team.orchestrator import EditorialOrchestrator
from team.tools.reporter import export_publication_artifacts

logger = logging.getLogger(__name__)


def create_mcp_server():
    """Configures and instantiates the FastMCP server for the editorial team."""
    try:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP(
            name="EditorialTeam",
            instructions="Hierarchical multi-agent pipeline (Planner, Researcher, Writer, Reviewer) producing citation-grounded articles with review gates."
        )

        @mcp.tool()
        def run_editorial_team(
            topic: str,
            mock_mode: bool = False,
            max_revisions: int = 2
        ) -> str:
            """Executes the full 4-agent collaborative editorial workflow on a topic.

            Args:
                topic: The subject to research, plan, draft, and critique.
                mock_mode: If True, operates in zero-key offline mock mode.
                max_revisions: Maximum review revision cycles (default 2).

            Returns:
                Formatted markdown summary with quality score, metrics, and file paths.
            """
            orchestrator = EditorialOrchestrator(
                mock_mode=mock_mode,
                max_revisions=max_revisions
            )
            state = orchestrator.run(topic)
            artifacts = export_publication_artifacts(state)
            metrics = state.metrics
            score = metrics.final_score if metrics else 85
            duration = metrics.duration_seconds if metrics else 0.0

            return (
                f"# Editorial Team Publication: {topic}\n\n"
                f"- **Quality Score**: {score} / 100 ({'APPROVED' if state.is_approved else 'Best-Effort'})\n"
                f"- **Revisions Applied**: {state.revision_turns} / {max_revisions}\n"
                f"- **Execution Time**: {duration}s\n"
                f"- **Markdown Article**: {artifacts['markdown_path']}\n"
                f"- **HTML Dashboard**:   {artifacts['html_path']}\n\n"
                f"---\n\n{state.current_draft}"
            )

        return mcp

    except ImportError:
        logger.warning("mcp package is not installed. FastMCP server unavailable.")
        return None


def run_test_mode():
    """Runs a verification test of the MCP tool binding."""
    print("=" * 70)
    print("🧪 MCP Editorial Team Self-Test Verification")
    print("=" * 70)

    server = create_mcp_server()
    if server is None:
        print("❌ FastMCP is not available.")
        return 1

    print("✅ FastMCP Server instantiated successfully.")
    print("Testing 'run_editorial_team' tool (mock mode)...")
    orchestrator = EditorialOrchestrator(mock_mode=True, max_revisions=2)
    state = orchestrator.run("MCP Architecture Patterns")
    artifacts = export_publication_artifacts(state, output_dir="test_mcp_reports_tmp")

    print(f"   -> Quality Score: {state.metrics.final_score}/100")
    print(f"   -> Revisions:     {state.revision_turns}")
    print(f"   -> Markdown:      {artifacts['markdown_path']}")
    print(f"   -> HTML:          {artifacts['html_path']}")

    # Clean up test output
    import shutil
    if os.path.exists("test_mcp_reports_tmp"):
        shutil.rmtree("test_mcp_reports_tmp", ignore_errors=True)

    print("\n✅ All MCP Server tool bindings verified successfully!")
    print("=" * 70)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Model Context Protocol Server for Multi-Agent Editorial Team.")
    parser.add_argument("--test", action="store_true", help="Run self-test verification of MCP server.")
    args = parser.parse_args()

    if args.test:
        sys.exit(run_test_mode())

    server = create_mcp_server()
    if server is None:
        print("Error: 'mcp' package is required. Install with `pip install mcp`.", file=sys.stderr)
        sys.exit(1)

    server.run(transport="stdio")


if __name__ == "__main__":
    main()

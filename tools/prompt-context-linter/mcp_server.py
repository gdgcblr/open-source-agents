"""FastMCP Server exposing Prompt Linter and Context Formatter tools."""

import json
import sys
from typing import Any, Dict

# Safe UTF-8 reconfiguration on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from linter.template_linter import PromptLinter
from linter.context_formatter import ContextFormatter
from linter.truncator import truncate_context, TruncationPolicy


def create_mcp_server():
    if FastMCP is None:
        return None

    mcp = FastMCP(
        "Prompt Context Linter",
        instructions="Developer utility for linting prompt templates, detecting prompt smells/injections, and managing context token budgets.",
    )

    @mcp.tool()
    def lint_prompt_template(
        template: str,
        variables_json: str = "{}",
        strict_mode: bool = False,
    ) -> str:
        """Statically inspects a prompt template for syntax, dangling braces, injection risks, and unclosed code blocks.

        Args:
            template: Prompt template string containing {variable} placeholders.
            variables_json: JSON string mapping variable names to their values.
            strict_mode: If true, treat missing variables as errors.

        Returns:
            JSON string containing is_valid, token estimates, and detailed issues.
        """
        try:
            vars_dict = json.loads(variables_json) if variables_json else {}
        except Exception:
            vars_dict = {}

        linter = PromptLinter(strict_mode=strict_mode)
        report = linter.lint(template, variables=vars_dict)
        return json.dumps(report.model_dump(), indent=2, default=str)

    @mcp.tool()
    def format_agent_context(
        system_role: str,
        instructions_json: str = "[]",
        user_query: str = "",
        delimiter_style: str = "markdown",
    ) -> str:
        """Constructs a clean, structured context prompt from modular components.

        Args:
            system_role: Core persona or objective.
            instructions_json: JSON array of instruction strings.
            user_query: The end user query or task.
            delimiter_style: 'markdown' (headings) or 'xml' (<tags>).

        Returns:
            Formatted prompt string.
        """
        try:
            instructions = json.loads(instructions_json)
        except Exception:
            instructions = []

        formatter = ContextFormatter(delimiter_style=delimiter_style)
        return formatter.build_context(
            system_role=system_role,
            instructions=instructions,
            user_query=user_query,
        )

    @mcp.tool()
    def truncate_context_budget(
        text: str,
        max_tokens: int,
        policy: str = "sandwich",
    ) -> str:
        """Truncates long document or prompt text to fit strict token budgets while preserving markdown syntax.

        Args:
            text: Source text to truncate.
            max_tokens: Target token budget.
            policy: 'head', 'tail', or 'sandwich'.

        Returns:
            JSON string with truncation metrics and truncated content.
        """
        result = truncate_context(
            text=text,
            max_tokens=max_tokens,
            policy=TruncationPolicy(policy),
        )
        return json.dumps(result.model_dump(), indent=2, default=str)

    return mcp


mcp_server = create_mcp_server()


def main():
    if "--test" in sys.argv:
        print("[MCP] Running Prompt Context Linter FastMCP self-test...")
        if mcp_server is None:
            print("[MCP ERROR] FastMCP is not installed in the environment.")
            sys.exit(1)

        # Self-test linting tool
        linter = PromptLinter()
        rep = linter.lint("Hello {name}!", {"name": "World"})
        assert rep.is_valid is True, "Valid template should pass"

        # Self-test truncator
        long_text = "word " * 1000
        trunc = truncate_context(long_text, max_tokens=50)
        assert trunc.truncated is True, "Long text should be truncated"

        print(f"[MCP SUCCESS] FastMCP server initialized: {mcp_server.name}")
        print(f"[MCP SUCCESS] Linter & Truncator self-tests passed cleanly.")
        sys.exit(0)

    if mcp_server:
        mcp_server.run()
    else:
        print("MCP SDK not installed. Run `pip install mcp`.")
        sys.exit(1)


if __name__ == "__main__":
    main()

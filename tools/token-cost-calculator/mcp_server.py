"""FastMCP Server exposing Token Usage and Multi-Provider Cost Calculator tools."""

import json
import sys

# Safe UTF-8 reconfiguration on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from calculator.analyzer import analyze_token_costs
from calculator.pricing import PRICING_REGISTRY, estimate_model_cost, list_supported_models
from calculator.tokenizer import count_tokens


def create_mcp_server():
    if FastMCP is None:
        return None

    mcp = FastMCP(
        "Token Cost Calculator",
        instructions="Multi-provider token usage auditor and cost estimation engine for AI agent workflows.",
    )

    @mcp.tool()
    def calculate_token_cost(
        text: str,
        model_id: str = "gemini-2.5-flash",
    ) -> str:
        """Estimates token counts and costs for a given prompt, transcript, or chat history.

        Args:
            text: Raw prompt, JSON chat history, or JSONL transcript.
            model_id: Model identifier (e.g. 'gemini-2.5-flash', 'gpt-4o', 'claude-3-5-sonnet').

        Returns:
            JSON string with token counts, prompt cost, and total estimated cost.
        """
        report = analyze_token_costs(text, primary_model_id=model_id)
        return json.dumps(
            {
                "model_id": report.primary_estimate.model_id,
                "provider": report.primary_estimate.provider,
                "token_breakdown": report.breakdown.model_dump(),
                "cost_usd": report.primary_estimate.model_dump(),
            },
            indent=2,
            default=str,
        )

    @mcp.tool()
    def compare_model_pricing(
        text: str,
        primary_model: str = "gemini-2.5-flash",
    ) -> str:
        """Compares token costs for a prompt or transcript across Google, OpenAI, Anthropic, and DeepSeek.

        Args:
            text: Raw prompt or transcript text.
            primary_model: The reference model.

        Returns:
            JSON string comparing costs, identifying the best-value model, and computing potential savings.
        """
        report = analyze_token_costs(text, primary_model_id=primary_model)
        return json.dumps(report.model_dump(), indent=2, default=str)

    @mcp.tool()
    def list_registered_models() -> str:
        """Returns the full catalog of registered LLM models, providers, context windows, and rates."""
        models = [p.model_dump() for p in PRICING_REGISTRY.values()]
        return json.dumps(models, indent=2)

    return mcp


mcp_server = create_mcp_server()


def main():
    if "--test" in sys.argv:
        print("[MCP] Running Token Cost Calculator FastMCP self-test...")
        if mcp_server is None:
            print("[MCP ERROR] FastMCP is not installed in the environment.")
            sys.exit(1)

        # Self-test token count and cost estimate
        sample = "Test prompt for self testing."
        toks = count_tokens(sample)
        assert toks > 0, "Token count should be positive"

        rep = analyze_token_costs(sample, primary_model_id="gemini-2.5-flash")
        assert rep.primary_estimate.total_cost_usd >= 0, "Cost estimate should be computed"
        assert len(rep.comparisons) >= 5, "Should compare across multiple models"

        print(f"[MCP SUCCESS] FastMCP server initialized: {mcp_server.name}")
        print(f"[MCP SUCCESS] Pricing & Token calculation self-test passed cleanly.")
        sys.exit(0)

    if mcp_server:
        mcp_server.run()
    else:
        print("MCP SDK not installed. Run `pip install mcp`.")
        sys.exit(1)


if __name__ == "__main__":
    main()

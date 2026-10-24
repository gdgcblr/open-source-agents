"""MCP server exposing prompt cost analysis tools."""

from mcp.server.fastmcp import FastMCP

from prompt_cost_analyzer.analyzer import analyze_prompt_cost
from prompt_cost_analyzer.pricing import list_model_rates

mcp = FastMCP("prompt-cost-analyzer")


@mcp.tool()
def list_supported_models() -> list[dict[str, str | float]]:
    """List built-in model rates, sources, and the date each rate was checked."""
    return list_model_rates()


@mcp.tool()
def estimate_prompt_cost(
    prompt: str,
    model: str,
    max_output_tokens: int,
    tool_results: list[str] | None = None,
    input_usd_per_million: float | None = None,
    output_usd_per_million: float | None = None,
) -> dict[str, object]:
    """Estimate text tokens and the maximum cost for one model request.

    Pass tool outputs as text in tool_results. For models without a built-in
    rate, provide both per-million-token prices. Either built-in rate can be
    overridden independently.
    """
    return analyze_prompt_cost(
        prompt=prompt,
        tool_results=[] if tool_results is None else tool_results,
        model=model,
        max_output_tokens=max_output_tokens,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
    )


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

"""Cost analysis, multi-model comparison, and ROI optimization engine."""

from typing import List, Optional
from .models import ComparisonReport, CostEstimate
from .parser import parse_content
from .pricing import PRICING_REGISTRY, estimate_model_cost


def analyze_token_costs(
    text_or_transcript: str,
    primary_model_id: str = "gemini-2.5-flash",
    source_label: str = "input_document",
    compare_models: Optional[List[str]] = None,
) -> ComparisonReport:
    """Performs end-to-end token analysis and multi-provider cost comparison.

    Args:
        text_or_transcript: Raw text, JSON chat, or JSONL transcript.
        primary_model_id: The main model being evaluated.
        source_label: Descriptive label for the source file.
        compare_models: Optional list of model IDs to compare against (defaults to all).

    Returns:
        ComparisonReport with token counts and pricing evaluations.
    """
    breakdown, fmt = parse_content(text_or_transcript)

    # Estimate primary model cost
    primary_est = estimate_model_cost(
        model_id=primary_model_id,
        prompt_tokens=breakdown.prompt_tokens,
        completion_tokens=breakdown.completion_tokens,
    )

    # Compare with other models
    targets = compare_models or sorted(list(PRICING_REGISTRY.keys()))
    comparisons: List[CostEstimate] = []
    for mid in targets:
        est = estimate_model_cost(
            model_id=mid,
            prompt_tokens=breakdown.prompt_tokens,
            completion_tokens=breakdown.completion_tokens,
        )
        comparisons.append(est)

    # Sort comparisons by total cost ascending
    comparisons.sort(key=lambda x: x.total_cost_usd)

    cheapest = comparisons[0]
    most_expensive = comparisons[-1]

    savings_usd = round(primary_est.total_cost_usd - cheapest.total_cost_usd, 6)
    if most_expensive.total_cost_usd > 0:
        savings_pct = round((1.0 - (cheapest.total_cost_usd / most_expensive.total_cost_usd)) * 100.0, 1)
    else:
        savings_pct = 0.0

    return ComparisonReport(
        source_label=source_label,
        source_format=fmt,
        breakdown=breakdown,
        primary_estimate=primary_est,
        comparisons=comparisons,
        cheapest_model_id=cheapest.model_id,
        max_savings_percentage=savings_pct,
        max_savings_usd=max(0.0, savings_usd),
    )

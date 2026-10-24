"""Provider pricing tables and cost calculation logic."""

from typing import Dict, List, Optional
from .models import CostEstimate, ModelPricing


PRICING_REGISTRY: Dict[str, ModelPricing] = {
    # Google Gemini
    "gemini-2.5-flash": ModelPricing(
        model_id="gemini-2.5-flash",
        provider="Google",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        cached_input_cost_per_million=0.01875,
        context_window=1000000,
    ),
    "gemini-1.5-flash": ModelPricing(
        model_id="gemini-1.5-flash",
        provider="Google",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        cached_input_cost_per_million=0.01875,
        context_window=1000000,
    ),
    "gemini-1.5-pro": ModelPricing(
        model_id="gemini-1.5-pro",
        provider="Google",
        input_cost_per_million=1.25,
        output_cost_per_million=5.00,
        cached_input_cost_per_million=0.3125,
        context_window=2000000,
    ),
    # OpenAI
    "gpt-4o": ModelPricing(
        model_id="gpt-4o",
        provider="OpenAI",
        input_cost_per_million=2.50,
        output_cost_per_million=10.00,
        cached_input_cost_per_million=1.25,
        context_window=128000,
    ),
    "gpt-4o-mini": ModelPricing(
        model_id="gpt-4o-mini",
        provider="OpenAI",
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        cached_input_cost_per_million=0.075,
        context_window=128000,
    ),
    "o3-mini": ModelPricing(
        model_id="o3-mini",
        provider="OpenAI",
        input_cost_per_million=1.10,
        output_cost_per_million=4.40,
        cached_input_cost_per_million=0.55,
        context_window=200000,
    ),
    # Anthropic
    "claude-3-5-sonnet": ModelPricing(
        model_id="claude-3-5-sonnet",
        provider="Anthropic",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        cached_input_cost_per_million=0.30,
        context_window=200000,
    ),
    "claude-3-5-haiku": ModelPricing(
        model_id="claude-3-5-haiku",
        provider="Anthropic",
        input_cost_per_million=0.80,
        output_cost_per_million=4.00,
        cached_input_cost_per_million=0.08,
        context_window=200000,
    ),
    # DeepSeek
    "deepseek-chat": ModelPricing(
        model_id="deepseek-chat",
        provider="DeepSeek",
        input_cost_per_million=0.14,
        output_cost_per_million=0.28,
        cached_input_cost_per_million=0.014,
        context_window=64000,
    ),
    "deepseek-reasoner": ModelPricing(
        model_id="deepseek-reasoner",
        provider="DeepSeek",
        input_cost_per_million=0.55,
        output_cost_per_million=2.19,
        cached_input_cost_per_million=0.14,
        context_window=64000,
    ),
}


def get_model_pricing(model_id: str) -> Optional[ModelPricing]:
    """Retrieves pricing specification for a model ID (case-insensitive lookup)."""
    norm = model_id.strip().lower()
    return PRICING_REGISTRY.get(norm)


def list_supported_models() -> List[str]:
    """Returns sorted list of all supported model identifiers."""
    return sorted(list(PRICING_REGISTRY.keys()))


def estimate_model_cost(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
) -> CostEstimate:
    """Calculates dollar cost for prompt and completion tokens on a specified model.

    Args:
        model_id: Model identifier (e.g. 'gemini-2.5-flash', 'gpt-4o').
        prompt_tokens: Number of prompt/input tokens.
        completion_tokens: Number of generated completion/output tokens.

    Returns:
        CostEstimate with breakdown and total USD cost.
    """
    pricing = get_model_pricing(model_id)
    if not pricing:
        # Fallback to standard baseline tier
        pricing = ModelPricing(
            model_id=model_id,
            provider="Custom/Unknown",
            input_cost_per_million=1.00,
            output_cost_per_million=3.00,
            context_window=128000,
        )

    prompt_cost = (prompt_tokens / 1_000_000.0) * pricing.input_cost_per_million
    comp_cost = (completion_tokens / 1_000_000.0) * pricing.output_cost_per_million
    total_cost = prompt_cost + comp_cost

    fits = (prompt_tokens + completion_tokens) <= pricing.context_window

    return CostEstimate(
        model_id=pricing.model_id,
        provider=pricing.provider,
        prompt_cost_usd=round(prompt_cost, 6),
        completion_cost_usd=round(comp_cost, 6),
        total_cost_usd=round(total_cost, 6),
        context_window=pricing.context_window,
        fits_context_window=fits,
    )

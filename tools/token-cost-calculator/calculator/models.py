"""Data models for Token Usage and Cost Calculator."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ModelPricing(BaseModel):
    """Pricing configuration per million tokens for an LLM provider model."""
    model_id: str
    provider: str
    input_cost_per_million: float
    output_cost_per_million: float
    cached_input_cost_per_million: Optional[float] = None
    context_window: int = 128000


class TokenBreakdown(BaseModel):
    """Token and character count breakdown."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_characters: int = 0
    message_count: int = 0


class CostEstimate(BaseModel):
    """Estimated cost calculation for a specific model."""
    model_id: str
    provider: str
    prompt_cost_usd: float
    completion_cost_usd: float
    total_cost_usd: float
    context_window: int
    fits_context_window: bool = True


class ComparisonReport(BaseModel):
    """Multi-model token and cost audit report."""
    source_label: str
    source_format: str
    breakdown: TokenBreakdown
    primary_estimate: CostEstimate
    comparisons: List[CostEstimate] = Field(default_factory=list)
    cheapest_model_id: str
    max_savings_percentage: float = 0.0
    max_savings_usd: float = 0.0

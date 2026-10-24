"""Token counting and maximum-completion cost estimates."""

from math import isfinite
from functools import lru_cache
from typing import Sequence

from prompt_cost_analyzer.pricing import resolve_rates

_TOKENS_PER_MILLION = 1_000_000


def analyze_prompt_cost(
    prompt: str,
    tool_results: Sequence[str],
    model: str,
    max_output_tokens: int,
    input_usd_per_million: float | None = None,
    output_usd_per_million: float | None = None,
) -> dict[str, object]:
    """Estimate prompt and tool-result tokens plus the maximum completion cost."""
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string.")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int):
        raise ValueError("max_output_tokens must be an integer.")
    if max_output_tokens < 0:
        raise ValueError("max_output_tokens must be zero or greater.")
    if not isinstance(tool_results, Sequence) or isinstance(tool_results, (str, bytes)):
        raise ValueError("tool_results must be a list of strings.")
    if any(not isinstance(result, str) for result in tool_results):
        raise ValueError("each tool result must be a string.")
    _validate_override("input_usd_per_million", input_usd_per_million)
    _validate_override("output_usd_per_million", output_usd_per_million)

    prompt_tokens = _count_tokens(prompt)
    tool_result_tokens = sum(_count_tokens(result) for result in tool_results)
    input_tokens = prompt_tokens + tool_result_tokens
    input_rate, output_rate, rate_source, pricing_note = resolve_rates(
        model,
        input_override=input_usd_per_million,
        output_override=output_usd_per_million,
    )
    input_cost = input_tokens * input_rate / _TOKENS_PER_MILLION
    max_output_cost = max_output_tokens * output_rate / _TOKENS_PER_MILLION

    return {
        "model": model,
        "tokenizer": "cl100k_base (approximation; provider tokenizers may differ)",
        "prompt_tokens": prompt_tokens,
        "tool_result_tokens": tool_result_tokens,
        "estimated_input_tokens": input_tokens,
        "max_output_tokens": max_output_tokens,
        "input_usd_per_million": input_rate,
        "output_usd_per_million": output_rate,
        "estimated_input_cost_usd": input_cost,
        "max_output_cost_usd": max_output_cost,
        "maximum_estimated_cost_usd": input_cost + max_output_cost,
        "pricing_source": rate_source,
        "pricing_note": pricing_note,
        "assumptions": [
            "The maximum cost assumes every allowed output token is generated.",
            "Provider message framing, tool schemas, caching, images, audio, and other "
            "non-text charges are not included.",
            "Pricing is a snapshot; confirm current provider rates before budgeting.",
        ],
    }


def _count_tokens(text: str) -> int:
    return len(_get_encoding().encode(text, disallowed_special=()))


@lru_cache(maxsize=1)
def _get_encoding():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def _validate_override(name: str, value: float | None) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a finite, non-negative number.")

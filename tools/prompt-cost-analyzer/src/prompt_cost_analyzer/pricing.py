"""Built-in model price snapshots and override handling."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ModelRate:
    input_usd_per_million: float
    output_usd_per_million: float
    source: str
    checked_on: str
    note: str


BUILT_IN_RATES: dict[str, ModelRate] = {
    # Anthropic Claude (Verified Current API Pricing)
    "claude-fable-5-1": ModelRate(
        input_usd_per_million=10.0,
        output_usd_per_million=50.0,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Most capable flagship reasoning tier; 1M context window; cache hits cost $0.25/M (2.5% of base).",
    ),
    "claude-opus-5-5": ModelRate(
        input_usd_per_million=4.0,
        output_usd_per_million=20.0,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Current flagship Opus tier; 1M context window; cache hits cost $0.20/M (5% of base).",
    ),
    "claude-sonnet-5-5": ModelRate(
        input_usd_per_million=2.0,
        output_usd_per_million=10.0,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Standard workhorse model; 1M context window; cache hits cost $0.10/M (5% of base).",
    ),
    "claude-haiku-5-5": ModelRate(
        input_usd_per_million=0.10,
        output_usd_per_million=0.50,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Ultra-fast tier for <=100k tokens ($0.50 / $2.50 for >100k context); 1M context window.",
    ),
    "claude-opus-4-6": ModelRate(
        input_usd_per_million=5.0,
        output_usd_per_million=25.0,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Standard input and output rates; cached tokens are not included.",
    ),
    "claude-sonnet-4-6": ModelRate(
        input_usd_per_million=3.0,
        output_usd_per_million=15.0,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Standard input and output rates; cached tokens are not included.",
    ),
    "claude-haiku-4-5": ModelRate(
        input_usd_per_million=1.0,
        output_usd_per_million=5.0,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        checked_on="2026-10-24",
        note="Standard input and output rates; cached tokens are not included.",
    ),
    "gemini-3-1-pro": ModelRate(
        input_usd_per_million=2.0,
        output_usd_per_million=12.0,
        source="https://ai.google.dev/pricing",
        checked_on="2026-10-24",
        note="Base rate for prompts <= 200k tokens; increases to $4.00 / $18.00 per million for > 200k context.",
    ),
    "gemini-3-8-flash": ModelRate(
        input_usd_per_million=0.75,
        output_usd_per_million=3.75,
        source="https://ai.google.dev/pricing",
        checked_on="2026-10-24",
        note="Promotional rate through Dec 31, 2026 ($1.50 / $7.50 standard rate starting Jan 1, 2027).",
    ),
    "gemini-3-1-flash-lite": ModelRate(
        input_usd_per_million=0.25,
        output_usd_per_million=1.50,
        source="https://ai.google.dev/pricing",
        checked_on="2026-10-24",
        note="Cheapest current-generation production model; context caching available at $0.025/M.",
    ),
    "gemini-3-pro-preview": ModelRate(
        input_usd_per_million=2.0,
        output_usd_per_million=10.0,
        source="https://ai.google.dev/gemini-api/docs/pricing",
        checked_on="2026-10-24",
        note="Standard paid tier through 2026-11-30; output includes thinking tokens.",
    ),
    "gemini-3-flash-preview": ModelRate(
        input_usd_per_million=0.75,
        output_usd_per_million=3.75,
        source="https://ai.google.dev/gemini-api/docs/pricing",
        checked_on="2026-10-24",
        note="Standard paid tier through 2026-12-31; output includes thinking tokens.",
    ),
    # OpenAI (Verified Current API Pricing)
    "gpt-6-astra": ModelRate(
        input_usd_per_million=10.0,
        output_usd_per_million=50.0,
        source="https://openai.com/api/pricing/",
        checked_on="2026-10-24",
        note="Flagship frontier model for deep reasoning and multi-agent workflows; cached reads at $1.00/M.",
    ),
    "gpt-6-1-sol": ModelRate(
        input_usd_per_million=2.0,
        output_usd_per_million=10.0,
        source="https://openai.com/api/pricing/",
        checked_on="2026-10-24",
        note="Standard workhorse model balancing performance and speed; cached reads at $0.10/M (5% of base).",
    ),
    "gpt-6-luna": ModelRate(
        input_usd_per_million=0.10,
        output_usd_per_million=0.50,
        source="https://openai.com/api/pricing/",
        checked_on="2026-10-24",
        note="Ultra-lightweight high-volume classification/extraction tier; cached reads at $0.01/M.",
    ),
    "gpt-5-6-sol": ModelRate(
        input_usd_per_million=4.0,
        output_usd_per_million=20.0,
        source="https://openai.com/api/pricing/",
        checked_on="2026-10-24",
        note="Previous flagship tier; promotional pricing available through Nov 2026.",
    ),
    # xAI Grok (Verified API Pricing)
    "grok-4-7": ModelRate(
        input_usd_per_million=2.0,
        output_usd_per_million=6.0,
        source="https://docs.x.ai/docs/overview#pricing",
        checked_on="2026-10-24",
        note="Current flagship model; 500k context; cached inputs cost $0.50/M; rate shifts to $4.00/$12.00 for prompts >= 200k tokens.",
    ),
    "grok-4-6": ModelRate(
        input_usd_per_million=2.0,
        output_usd_per_million=6.0,
        source="https://docs.x.ai/docs/overview#pricing",
        checked_on="2026-10-24",
        note="Previous flagship tier; 500k context window; cached inputs cost $0.50/M.",
    ),
    "grok-4-3": ModelRate(
        input_usd_per_million=1.25,
        output_usd_per_million=2.50,
        source="https://docs.x.ai/docs/overview#pricing",
        checked_on="2026-10-24",
        note="Budget general-purpose model; 1M context window; cached inputs cost $0.20/M.",
    ),
    "grok-build-0-1": ModelRate(
        input_usd_per_million=1.0,
        output_usd_per_million=2.0,
        source="https://docs.x.ai/docs/overview#pricing",
        checked_on="2026-10-24",
        note="Coding-agent targeted model; 256k context window; cached inputs cost $0.20/M.",
    ),
}


def list_model_rates() -> list[dict[str, str | float]]:
    """Return built-in rates and their provenance for discovery."""
    return [
        {
            "model": model,
            "input_usd_per_million": rate.input_usd_per_million,
            "output_usd_per_million": rate.output_usd_per_million,
            "source": rate.source,
            "checked_on": rate.checked_on,
            "note": rate.note,
        }
        for model, rate in sorted(BUILT_IN_RATES.items())
    ]


def resolve_rates(
    model: str,
    input_override: float | None = None,
    output_override: float | None = None,
) -> tuple[float, float, str, str | None]:
    """Resolve built-in rates, applying any per-call override."""
    built_in = BUILT_IN_RATES.get(model)
    if built_in is None and (input_override is None or output_override is None):
        raise ValueError(
            f"No built-in price for {model!r}; provide both input and output "
            "rates in USD per million tokens."
        )

    input_rate = (
        built_in.input_usd_per_million if input_override is None else input_override
    )
    output_rate = (
        built_in.output_usd_per_million if output_override is None else output_override
    )
    _validate_rate("input_usd_per_million", input_rate)
    _validate_rate("output_usd_per_million", output_rate)

    if built_in is None:
        return input_rate, output_rate, "user-supplied", None
    source = built_in.source if input_override is None and output_override is None else (
        f"built-in snapshot ({built_in.source}); overridden rates are user-supplied"
    )
    return input_rate, output_rate, source, built_in.note


def _validate_rate(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative number.")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number.")

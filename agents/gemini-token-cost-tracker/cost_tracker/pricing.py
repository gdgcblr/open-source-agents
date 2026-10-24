"""Pure cost math. No network, no API key needed."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PRICING_PATH = Path(__file__).resolve().parent.parent / "pricing.json"


def load_pricing(path: str | None = None) -> dict:
    p = Path(path or os.getenv("TRACKER_PRICING_FILE", DEFAULT_PRICING_PATH))
    with open(p, encoding="utf-8") as f:
        return json.load(f)["models"]


def resolve_model(model: str, table: dict) -> str | None:
    """Map 'models/gemini-2.5-flash-001' or 'gemini-2.5-flash-preview' to a table key."""
    name = model.removeprefix("models/").strip().lower()
    if name in table:
        return name
    # longest key that prefixes the name wins (so flash-lite beats flash)
    matches = [k for k in table if name.startswith(k)]
    return max(matches, key=len) if matches else None


def calculate_cost(
    model: str,
    prompt_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
    cached_tokens: int = 0,
    table: dict | None = None,
) -> dict:
    """Cost in USD. Thinking tokens bill at the output rate.
    `prompt_tokens` includes cached tokens (as Gemini's usage_metadata reports it)."""
    table = table or load_pricing()
    key = resolve_model(model, table)
    if key is None:
        return {"model": model, "known_model": False, "cost_usd": 0.0,
                "error": f"No pricing for '{model}'. Add it to pricing.json."}
    rates = table[key]
    in_rate, out_rate = rates["input"], rates["output"]
    lc = rates.get("long_context")
    if lc and prompt_tokens > lc["threshold"]:
        in_rate, out_rate = lc["input"], lc["output"]
    cached_rate = rates.get("cached_input", in_rate * 0.1)

    cached = min(cached_tokens, prompt_tokens)
    fresh = prompt_tokens - cached
    billable_out = output_tokens + thinking_tokens

    input_cost = fresh * in_rate / 1e6
    cached_cost = cached * cached_rate / 1e6
    output_cost = billable_out * out_rate / 1e6
    return {
        "model": key,
        "known_model": True,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "input_cost_usd": round(input_cost, 8),
        "cached_cost_usd": round(cached_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "cost_usd": round(input_cost + cached_cost + output_cost, 8),
    }

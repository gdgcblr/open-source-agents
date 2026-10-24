"""Function tools exposed to the ADK agent. Docstrings are the tool descriptions
the LLM sees, so keep them precise. All return JSON-serialisable dicts."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from . import store
from .pricing import calculate_cost, load_pricing


def _client():
    from google import genai  # imported lazily so tests run without credentials
    return genai.Client()


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  thinking_tokens: int = 0, cached_tokens: int = 0) -> dict:
    """Calculate the USD cost of a Gemini call from token counts.

    Args:
        model: Gemini model id, e.g. 'gemini-2.5-flash'.
        input_tokens: Total prompt tokens (including any cached tokens).
        output_tokens: Visible response tokens.
        thinking_tokens: Hidden reasoning tokens (billed as output).
        cached_tokens: Prompt tokens served from cache (billed at a discount).
    """
    return calculate_cost(model, input_tokens, output_tokens, thinking_tokens, cached_tokens)


def count_tokens(text: str, model: str = "gemini-3.8-flash") -> dict:
    """Count how many tokens a piece of text uses for a Gemini model, and the
    input cost. Falls back to a ~4 chars/token estimate if the API is unavailable.

    Args:
        text: The text to measure.
        model: Gemini model id.
    """
    estimated = False
    try:
        n = _client().models.count_tokens(model=model, contents=text).total_tokens
    except Exception:
        n, estimated = max(1, len(text) // 4), True
    cost = calculate_cost(model, n, 0)
    return {"model": model, "tokens": n, "estimated": estimated,
            "input_cost_usd": cost.get("input_cost_usd", 0.0)}


def track_prompt(prompt: str, model: str = "gemini-3.8-flash") -> dict:
    """Send a prompt to Gemini, then log its real token usage and cost.
    Use when the user wants to run a prompt and see what it cost.

    Args:
        prompt: The prompt to send.
        model: Gemini model id to run it on.
    """
    resp = _client().models.generate_content(model=model, contents=prompt)
    u = resp.usage_metadata
    prompt_t = getattr(u, "prompt_token_count", 0) or 0
    out_t = getattr(u, "candidates_token_count", 0) or 0
    think_t = getattr(u, "thoughts_token_count", 0) or 0
    cached_t = getattr(u, "cached_content_token_count", 0) or 0
    cost = calculate_cost(model, prompt_t, out_t, think_t, cached_t)
    store.record("track_prompt", cost["model"], prompt_t, out_t, think_t, cached_t,
                 cost["cost_usd"], hashlib.sha256(prompt.encode()).hexdigest()[:16])
    return {"response_preview": (resp.text or "")[:500], **cost}


def compare_models(input_tokens: int, output_tokens: int) -> dict:
    """Show what the same workload would cost on every known Gemini model,
    cheapest first.

    Args:
        input_tokens: Prompt tokens per call.
        output_tokens: Output tokens per call.
    """
    table = load_pricing()
    rows = [calculate_cost(m, input_tokens, output_tokens, table=table) for m in table]
    rows.sort(key=lambda r: r["cost_usd"])
    cheapest = rows[0]["cost_usd"] or 1e-12
    return {"per_call": [{"model": r["model"], "cost_usd": r["cost_usd"],
                          "x_cheapest": round(r["cost_usd"] / cheapest, 1)} for r in rows]}


def get_usage_report(days: int = 7) -> dict:
    """Summarise tracked token usage and spend over the last N days, by model.

    Args:
        days: Look-back window in days.
    """
    rows = store.rows_since(days)
    if not rows:
        return {"days": days, "calls": 0, "total_cost_usd": 0.0, "by_model": []}
    agg = defaultdict(lambda: {"calls": 0, "prompt": 0, "output": 0, "thinking": 0, "cost": 0.0})
    for r in rows:
        a = agg[r["model"]]
        a["calls"] += 1
        a["prompt"] += r["prompt_tokens"]
        a["output"] += r["output_tokens"]
        a["thinking"] += r["thinking_tokens"]
        a["cost"] += r["cost_usd"]
    by_model = [{"model": m, "calls": a["calls"], "prompt_tokens": a["prompt"],
                 "output_tokens": a["output"], "thinking_tokens": a["thinking"],
                 "cost_usd": round(a["cost"], 6)}
                for m, a in sorted(agg.items(), key=lambda kv: -kv[1]["cost"])]
    return {"days": days, "calls": len(rows),
            "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
            "by_model": by_model}


def suggest_optimizations(days: int = 7) -> dict:
    """Analyse tracked usage and return concrete, quantified ways to cut cost:
    cheaper-model swaps, thinking-token reduction, caching for repeated prompts,
    and output-length limits. Always call this before giving cost-saving advice.

    Args:
        days: Look-back window in days.
    """
    table = load_pricing()
    rows = store.rows_since(days)
    tips = []
    if not rows:
        return {"days": days, "tips": [], "note": "No usage tracked yet."}

    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)

    # 1) Cheaper model swap
    for model, rs in by_model.items():
        alt = table.get(model, {}).get("cheaper_alternative")
        if not alt:
            continue
        now = sum(r["cost_usd"] for r in rs)
        then = sum(calculate_cost(alt, r["prompt_tokens"], r["output_tokens"],
                                  r["thinking_tokens"], r["cached_tokens"], table)["cost_usd"] for r in rs)
        if now > 0 and (now - then) / now > 0.3:
            tips.append({"type": "downgrade_model", "model": model, "alternative": alt,
                         "current_usd": round(now, 4), "projected_usd": round(then, 4),
                         "savings_usd": round(now - then, 4),
                         "advice": f"Try {alt} for simple tasks; validate quality first."})

    # 2) Thinking-token share
    for model, rs in by_model.items():
        think = sum(r["thinking_tokens"] for r in rs)
        out = sum(r["output_tokens"] for r in rs)
        if think + out and think / (think + out) > 0.5:
            rate = table.get(model, {}).get("output", 0)
            tips.append({"type": "reduce_thinking", "model": model,
                         "thinking_share": round(think / (think + out), 2),
                         "savings_usd": round(think * rate / 1e6 * 0.5, 4),
                         "advice": "Over half of output tokens are hidden reasoning. "
                                   "Lower the thinking budget for routine prompts."})

    # 3) Repeated large prompts -> context caching
    groups = defaultdict(list)
    for r in rows:
        if r["prompt_hash"]:
            groups[(r["prompt_hash"], r["model"])].append(r)
    for (_, model), rs in groups.items():
        n, tok = len(rs), rs[0]["prompt_tokens"]
        if n >= 3 and tok >= 1024 and model in table:
            m = table[model]
            saved = (n - 1) * tok * (m["input"] - m.get("cached_input", m["input"] * 0.1)) / 1e6
            tips.append({"type": "use_context_caching", "model": model, "repeats": n,
                         "prompt_tokens": tok, "savings_usd": round(saved, 4),
                         "advice": "Same large prompt sent repeatedly. Cache the shared prefix."})

    # 4) Long outputs
    for model, rs in by_model.items():
        avg_out = sum(r["output_tokens"] for r in rs) / len(rs)
        if avg_out > 1000:
            tips.append({"type": "limit_output", "model": model, "avg_output_tokens": round(avg_out),
                         "advice": "Set max_output_tokens or ask for concise answers. "
                                   "Output tokens cost several times more than input."})

    tips.sort(key=lambda t: -t.get("savings_usd", 0))
    return {"days": days, "tips": tips,
            "total_potential_savings_usd": round(sum(t.get("savings_usd", 0) for t in tips), 4)}


def set_budget(daily_usd: float) -> dict:
    """Set a daily spending budget in USD for tracked Gemini usage.

    Args:
        daily_usd: Maximum USD to spend per day.
    """
    store.set_setting("daily_budget_usd", daily_usd)
    return {"daily_budget_usd": daily_usd}


def check_budget() -> dict:
    """Compare the last 24 hours of tracked spend against the daily budget."""
    budget = store.get_setting("daily_budget_usd")
    spent = sum(r["cost_usd"] for r in store.rows_since(1))
    if budget is None:
        return {"spent_24h_usd": round(spent, 6), "budget_set": False}
    budget = float(budget)
    return {"spent_24h_usd": round(spent, 6), "daily_budget_usd": budget,
            "percent_used": round(100 * spent / budget, 1) if budget else None,
            "over_budget": spent > budget}

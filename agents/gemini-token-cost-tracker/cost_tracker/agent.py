import os

from dotenv import load_dotenv
from google.adk.agents import Agent

from . import store
from .pricing import calculate_cost
from .tools import (check_budget, compare_models, count_tokens, estimate_cost,
                    get_usage_report, set_budget, suggest_optimizations, track_prompt)

load_dotenv()
MODEL = os.getenv("TRACKER_MODEL", "gemini-3.8-flash")


def log_own_usage(callback_context, llm_response):
    """After every model call the agent itself makes, record its own token cost.
    The tracker therefore tracks itself."""
    try:
        u = getattr(llm_response, "usage_metadata", None)
        if u is None or getattr(llm_response, "partial", False):
            return None
        p = getattr(u, "prompt_token_count", 0) or 0
        o = getattr(u, "candidates_token_count", 0) or 0
        t = getattr(u, "thoughts_token_count", 0) or 0
        c = getattr(u, "cached_content_token_count", 0) or 0
        cost = calculate_cost(MODEL, p, o, t, c)
        store.record("agent-self", cost["model"], p, o, t, c, cost["cost_usd"])
    except Exception:
        pass  # never break the agent because logging failed
    return None


root_agent = Agent(
    name="gemini_token_cost_tracker",
    model=MODEL,
    description="Tracks Gemini token usage and cost, and recommends how to cut it.",
    instruction="""You are a FinOps assistant for Gemini API usage.

Rules:
- Never guess token counts or costs. Use tools for every number.
- To price a prompt before sending it: count_tokens. To run and measure it: track_prompt.
- For "what did I spend" questions: get_usage_report.
- For "how can I save money": ALWAYS call suggest_optimizations first, then explain
  the top tips in plain language with the dollar savings from the tool output.
- For model choice questions: compare_models.
- Handle budgets with set_budget / check_budget, and warn clearly when over budget.
- Prices live in pricing.json and can be stale. Mention this once if the user asks about exact billing.
- Keep answers short. Lead with the number, then the advice. Format money like $0.0042.""",
    tools=[estimate_cost, count_tokens, track_prompt, compare_models,
           get_usage_report, suggest_optimizations, set_budget, check_budget],
    after_model_callback=log_own_usage,
)

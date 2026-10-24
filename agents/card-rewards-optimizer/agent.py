"""LLM layer: Gemini does goal parsing, numbers-free optimize narration, and chat
planning. Every figure comes from engine.py; `optimize` narration carries no numbers
at all, and chat may only quote numbers a tool actually returned (verify_numbers)."""
from __future__ import annotations

import os
import re
import time

from engine import CATEGORIES, DISCLAIMER, format_table, rank_routes
from portfolio import Portfolio, RatesData

_AUTH_MARKERS = ("api key", "api_key", "unauthenticated", "permission", "invalid key")
_RETRYABLE_MARKERS = ("429", "rate", "quota", "resource exhausted", "500", "502",
                      "503", "unavailable", "timeout", "deadline")


class AgentError(Exception):
    """A Gemini call failed in a way the user should see as a clean message, not a
    traceback. Raised by _generate_with_retry; caught in main.py and chat."""


def get_client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    from google import genai
    from google.genai import types
    # Bound each request so a network stall becomes a retryable timeout, not a hang.
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30_000))


def model_name() -> str:
    return os.environ.get("MODEL_NAME", "gemini-3.5-flash")


def _generate_with_retry(client, contents: str, _sleep=time.sleep) -> str:
    """One call plus one backoff retry on transient errors (429/5xx/timeout). Auth
    errors are never retried. Every failure becomes an AgentError carrying context —
    this broad catch is deliberate translation-and-re-raise of the SDK's heterogeneous
    exception types, never a swallow. `_sleep` is injectable so tests run instantly."""
    last = None
    for attempt in range(2):
        try:
            resp = client.models.generate_content(model=model_name(), contents=contents)
            return resp.text or ""
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in _AUTH_MARKERS):
                raise AgentError("Gemini rejected the API key — check GEMINI_API_KEY "
                                 "(free key: https://aistudio.google.com/apikey).") from e
            if attempt == 0 and any(k in msg for k in _RETRYABLE_MARKERS):
                last = e
                _sleep(2)
                continue
            raise AgentError(f"Gemini request failed: {e}") from e
    raise AgentError(f"Gemini request failed after retry: {last}")


def parse_goal_category(client, goal: str) -> str | None:
    prompt = (
        "Classify this credit-card redemption goal into exactly one category.\n"
        f"Categories: {', '.join(CATEGORIES)}\n"
        f"Goal: {goal!r}\n"
        "Answer with the single category word only.")
    reply = _generate_with_retry(client, prompt).strip().lower()
    if reply in CATEGORIES:
        return reply
    # tolerate decoration — "Category: cash", "**cash**", "cash back"
    tokens = set(re.findall(r"[a-z]+", reply))
    hits = [c for c in CATEGORIES if c in tokens]
    return hits[0] if len(hits) == 1 else None


def as_of_numbers(rates: RatesData) -> set[float]:
    """The only numbers allowed in a numbers-free optimize narration: the dataset
    date. '2026-10-24' -> {2026.0, 10.0, 24.0}."""
    return {float(p) for p in rates.as_of.split("-") if p.isdigit()}


def verify_numbers(text: str, allowed: set[float]) -> list[float]:
    """Return every number in `text` not matching anything in `allowed` (commas
    ignored; tolerance tight enough to catch a fabricated per-point rate like 0.80
    vs 0.75, loose enough to absorb float repr on large totals). Empty list means
    grounded. Two callers: optimize passes only as_of_numbers (narration must stay
    numbers-free); chat passes a set seeded with the date and grown from each tool
    result, so the model may only quote numbers a tool actually returned."""
    bad: list[float] = []
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        n = float(token.replace(",", ""))
        if not any(abs(n - a) <= max(0.005, 1e-4 * a) for a in allowed):
            bad.append(n)
    return bad


def run_optimize_narration(goal: str, portfolio: Portfolio, rates: RatesData) -> bool:
    """Numbers-free narrated optimize. The model writes only the qualitative
    recommendation; engine.py's table below carries every figure, so a wrong number
    is structurally impossible. Returns False with no API key (caller shows the plain
    table). Raises AgentError on a Gemini failure (main.py turns it into a clean
    message; `optimize --category` gives the numbers offline)."""
    client = get_client()
    if client is None:
        return False
    category = parse_goal_category(client, goal)
    vals = rank_routes(portfolio, rates, category) if category else rank_routes(portfolio, rates)
    if not vals:
        print(f"No {category} routes available for your cards/balances.")
        return True
    table = format_table(vals, rates.as_of)
    top = vals[0]
    facts = f"Best route: {top.card_name} via {top.route.partner or top.route.id}."
    if len(vals) > 1:
        r = vals[1]
        facts += f" Runner-up: {r.card_name} via {r.route.partner or r.route.id}."
    ask = (
        "You are a credit-card rewards assistant. Write a 3-5 sentence recommendation "
        f"for the goal {goal!r}: say which route is best and why, and mention the "
        "runner-up. IMPORTANT: do NOT include any numbers, digits, amounts, or rates "
        "— a table beneath your text shows every figure. Speak qualitatively "
        "('the strongest value', 'clearly ahead').\n" + facts)
    narration = _generate_with_retry(client, ask)
    if verify_numbers(narration, as_of_numbers(rates)):
        narration = _generate_with_retry(
            client, ask + "\n\nYour previous answer contained digits. Rewrite with NO numbers at all.")
    if verify_numbers(narration, as_of_numbers(rates)):
        print(table)                 # couldn't get a clean numbers-free narration; table is the source of truth
        return True
    print(narration.strip())
    print(f"\n{table}")
    return True


CHAT_SYSTEM = (
    "You are a grounded credit-card rewards assistant for Indian cards. Rules: "
    "(1) Only quote numbers returned by your tools — never from memory. "
    "(2) Always state the dataset as_of date when quoting rates. "
    "(3) If a question needs data outside the dataset, say so plainly. "
    f"(4) End substantive answers with: {DISCLAIMER}")


def chat_system(portfolio: Portfolio, rates: RatesData) -> str:
    """Full system instruction: the rules plus the user's actual holdings (card_id,
    name, and balance). The model needs the slug to call tools and the balance to
    pass as the `points` argument to calculate_redemption_value — otherwise it can't
    answer 'what are my points worth' and correctly refuses rather than guess."""
    held = "; ".join(f"{h.card_id} ({rates.cards[h.card_id].name}): {h.points} points"
                     for h in portfolio.holdings)
    return (CHAT_SYSTEM + " The user's holdings — always pass the card_id slug (not the "
            "display name) to tools, and use the matching balance as the `points` "
            f"argument to calculate_redemption_value: {held}.")


def make_tools(portfolio: Portfolio, rates: RatesData,
               call_log: list, numbers_seen: set):
    from engine import expiring_points

    def lookup_transfer_rates(card_id: str) -> dict:
        """List every redemption route for a card id (e.g. 'hdfc-infinia'),
        with partner, transfer ratio, indicative INR value per point, minimums."""
        call_log.append("lookup_transfer_rates")
        card = rates.cards.get(card_id)
        if card is None:
            return {"error": f"unknown card_id. Valid: {sorted(rates.cards)}"}
        for r in card.routes:
            numbers_seen.update({float(r.min_points), float(r.value_inr_per_point)})
            if r.transfer_ratio:
                numbers_seen.update(float(p) for p in re.findall(r"\d+", r.transfer_ratio))
        return {"card": card.name, "as_of": rates.as_of, "routes": [
            {"route_id": r.id, "category": r.category, "partner": r.partner,
             "transfer_ratio": r.transfer_ratio,
             "value_inr_per_point": r.value_inr_per_point,
             "min_points": r.min_points} for r in card.routes]}

    def calculate_redemption_value(card_id: str, route_id: str, points: int) -> dict:
        """Compute the INR value of redeeming `points` from a card via a route_id."""
        call_log.append("calculate_redemption_value")
        card = rates.cards.get(card_id)
        if card is None:
            return {"error": f"unknown card_id. Valid: {sorted(rates.cards)}"}
        route = next((r for r in card.routes if r.id == route_id), None)
        if route is None:
            return {"error": f"unknown route_id. Valid: {[r.id for r in card.routes]}"}
        if points < route.min_points:
            return {"error": f"route needs at least {route.min_points} points"}
        total = round(points * route.value_inr_per_point, 2)
        numbers_seen.update({float(points), total, float(round(total)),
                             float(route.value_inr_per_point)})
        return {"card": card.name, "route_id": route_id, "points": points,
                "value_inr_per_point": route.value_inr_per_point,
                "total_value_inr": total, "as_of": rates.as_of}

    def check_expiry() -> dict:              # dict, not a bare list (AFC re-wraps lists)
        """List the user's point batches expiring within 90 days, with best use."""
        call_log.append("check_expiry")
        alerts = expiring_points(portfolio, rates)
        for a in alerts:
            numbers_seen.update({float(a.points), float(a.days_left)})
            if a.best is not None:
                numbers_seen.add(a.best.total_value_inr)
        return {"alerts": [
            {"card": a.card_name, "points": a.points,
             "expires_on": a.expires_on.isoformat(), "days_left": a.days_left,
             "best_route": (a.best.route.partner or a.best.route.id) if a.best else None}
            for a in alerts]}

    return [lookup_transfer_rates, calculate_redemption_value, check_expiry]


def run_chat(portfolio: Portfolio, rates: RatesData) -> None:
    from google.genai import types
    client = get_client()
    call_log: list = []
    numbers_seen: set = as_of_numbers(rates)   # seed with the date only; grows from tool results
    tools = make_tools(portfolio, rates, call_log, numbers_seen)
    chat = client.chats.create(model=model_name(), config=types.GenerateContentConfig(
        tools=tools, system_instruction=chat_system(portfolio, rates)))
    print("Grounded rewards chat. Ctrl-C / Ctrl-D or 'quit' to exit.")
    while True:
        try:
            msg = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg or msg.lower() in {"quit", "exit"}:
            break
        try:
            resp = chat.send_message(msg)
            text = resp.text or ""
            bad = verify_numbers(text, numbers_seen)
            if bad:
                resp = chat.send_message(
                    f"Your answer used numbers not returned by any tool: {bad}. "
                    "Re-answer using only tool-returned numbers, exactly.")
                text = resp.text or ""
                bad = verify_numbers(text, numbers_seen)
            if bad:                         # refuse to show known-ungrounded numbers
                print("\nagent> I couldn't ground that in the dataset — try "
                      "`optimize --category flights|hotels|cash|shopping` for exact figures.")
            else:
                print(f"\nagent> {text.strip()}")
        except KeyboardInterrupt:
            print("\n(interrupted — type 'quit' to exit)")
        except Exception as e:              # keep the session alive on a transient API error
            if any(k in str(e).lower() for k in _AUTH_MARKERS):
                print("\nGemini rejected the API key — exiting chat. Check GEMINI_API_KEY.")
                break
            print(f"\n(Gemini request failed: {e} — try again.)")

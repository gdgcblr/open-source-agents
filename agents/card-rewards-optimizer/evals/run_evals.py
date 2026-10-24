"""Golden-set evals for the LLM layer. Deterministic checks, live model calls.
Usage: python evals/run_evals.py [--sleep SECONDS]
  (from the project root, GEMINI_API_KEY set). Use --sleep ~13 to stay under the
  Gemini free-tier 5-requests/min limit."""
import argparse
import sys
import time
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from agent import get_client, make_tools, model_name, parse_goal_category  # noqa: E402
from engine import rank_routes  # noqa: E402
from portfolio import load_portfolio, load_rates  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="seconds to pause between cases (use ~13 on the free tier)")
    args = parser.parse_args(argv)

    client = get_client()
    if client is None:
        print("GEMINI_API_KEY required for evals")
        return 2
    rates = load_rates(str(BASE / "data" / "transfer_rates.yaml"))
    portfolio = load_portfolio(str(BASE / "examples" / "portfolio.yaml"), rates)
    cases = yaml.safe_load(open(BASE / "evals" / "cases.yaml"))
    passed = total = 0

    for case in cases["goal_cases"]:
        total += 1
        got = parse_goal_category(client, case["goal"])
        ranked = rank_routes(portfolio, rates, got) if got else []   # no IndexError
        top = ranked[0] if ranked else None
        ok = (got == case["expected_category"] and top is not None
              and top.card_id == case["expected_card_id"]
              and top.route.id == case["expected_route_id"])
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] goal: {case['goal']!r} -> {got}")
        time.sleep(args.sleep)

    from google.genai import types
    from agent import chat_system          # evals must exercise the prod system prompt
    for case in cases["chat_cases"]:
        total += 1
        call_log, numbers = [], set()
        tools = make_tools(portfolio, rates, call_log, numbers)
        chat = client.chats.create(model=model_name(), config=types.GenerateContentConfig(
            tools=tools, system_instruction=chat_system(portfolio, rates)))
        chat.send_message(case["question"])
        ok = case["expected_tool"] in call_log
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] chat: {case['question']!r} -> {call_log}")
        time.sleep(args.sleep)

    print(f"\n{passed}/{total} passed on {model_name()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

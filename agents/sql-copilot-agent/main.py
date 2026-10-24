"""CLI entry point for the SQL Copilot agent.

Usage:
    python main.py --query "Which city has the most customers?"
    python main.py                      # interactive REPL
    python main.py --demo               # read-only sample questions
    python main.py --write-demo         # create/update records in plain English
    python main.py --yes                # auto-confirm writes (skip the prompt)
    python main.py --reset-db           # recreate the demo database
"""

from __future__ import annotations

import argparse
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars still work without it.
    pass

from agent import SqlCopilotAgent
from database import seed_database, set_confirm_hook

DEMO_QUESTIONS = [
    "Which city has the most customers?",
    "What is the total revenue from delivered orders?",
    "Who are the top 3 customers by number of orders?",
    "Which product category sold the most units?",
    "How many orders were cancelled?",
]

# Plain-English instructions that CHANGE data — no form, just words.
WRITE_DEMO_INSTRUCTIONS = [
    "Place a new order for Aarav Sharma for 2 Mechanical Keyboards and "
    "1 USB-C Hub, dated today (2026-10-24) with status 'placed'.",
    "Cancel the order we just created for Aarav.",
]

_RULE = "-" * 68


def _make_confirm_hook(auto_yes: bool):
    """Return a confirmation callback for writes (human-in-the-loop)."""

    def _confirm(summary: str, statements: list[str]) -> bool:
        print("\n  ⚠  This will WRITE to the database:")
        if summary:
            print(f"     {summary}")
        for stmt in statements:
            print(f"       - {stmt}")
        if auto_yes:
            print("     (auto-confirmed via --yes)")
            return True
        try:
            answer = input("     Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in {"y", "yes"}

    return _confirm


def _run_one(agent: SqlCopilotAgent, prompt: str) -> None:
    print(f"\n> {prompt}")
    print(_RULE)
    result = agent.ask(prompt)
    print(_RULE)
    print(f"A: {result.answer}")
    print(f"   ({result.steps} step(s))")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQL Copilot — talk to your database in plain English.")
    parser.add_argument("--query", "-q", help="A single natural-language instruction (read or write).")
    parser.add_argument("--demo", action="store_true", help="Run read-only sample questions.")
    parser.add_argument("--write-demo", action="store_true", help="Run plain-English create/update examples.")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm writes (skip the prompt).")
    parser.add_argument("--reset-db", action="store_true", help="Recreate the demo database and exit.")
    parser.add_argument("--quiet", action="store_true", help="Hide the step-by-step agent trace.")
    args = parser.parse_args(argv)

    if args.reset_db:
        seed_database(force=True)
        print("Demo database recreated.")
        return 0

    seed_database()
    set_confirm_hook(_make_confirm_hook(auto_yes=args.yes))

    try:
        agent = SqlCopilotAgent(verbose=not args.quiet)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.demo:
        for question in DEMO_QUESTIONS:
            _run_one(agent, question)
        return 0

    if args.write_demo:
        for instruction in WRITE_DEMO_INSTRUCTIONS:
            _run_one(agent, instruction)
        return 0

    if args.query:
        _run_one(agent, args.query)
        return 0

    # Interactive REPL.
    print("SQL Copilot — talk to your database in plain English. Type 'exit' to quit.")
    while True:
        try:
            prompt = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if prompt.lower() in {"exit", "quit", ""}:
            break
        _run_one(agent, prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

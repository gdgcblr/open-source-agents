"""End-to-end demo runner against REAL GitHub accounts.

Runs the full agent pipeline (live GitHub fetch -> grounding guardrail ->
digest) for a set of well-known public users, so you can see the agent working
against genuine data without constructing anything by hand.

By default it uses the deterministic `mock` LLM so the demo is reproducible and
needs no model server or API key. Point it at a real model with --provider:

    python scripts/demo.py                       # live GitHub + mock LLM
    python scripts/demo.py --provider ollama     # live GitHub + local Ollama
    python scripts/demo.py --user octocat --date 2026-10-04

Set GITHUB_TOKEN in your environment to avoid the low anonymous rate limit.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except Exception:  # noqa: BLE001
    pass

from standup.agent import StandupAgent          # noqa: E402
from standup.github_tool import GitHubTool       # noqa: E402
from standup.llm import get_provider             # noqa: E402

# Public accounts that reliably have recent, varied activity on the pinned
# dates below. These are real maintainers; we only read their public event feed.
# NOTE: GitHub's public Events API only exposes ~the last 90 days, so these
# pinned dates will eventually fall out of the window and return 0 events (which
# the agent then correctly escalates). Pass --user/--date for a current run.
DEFAULT_TARGETS = [
    ("torvalds", "2026-10-04"),    # busy day across linux + a side project
    ("gaearon", "2026-10-21"),     # busy day
    ("sindresorhus", "2026-10-23"),  # busy day
]


def run_one(agent: StandupAgent, tool: GitHubTool, user: str, date: str) -> None:
    print("\n" + "=" * 68)
    print(f"LIVE RUN: {user} @ {date}")
    print("=" * 68)
    log = tool.fetch_day(user, date)
    print(f"Fetched {len(log.events)} real event(s) from GitHub"
          + (" (PARTIAL)" if log.partial else ""))
    digest = agent.generate(log)
    print()
    print(digest.text)
    if digest.needs_confirmation:
        print("\nNeeds confirmation:")
        for item in digest.needs_confirmation:
            print(f"  ? {item}")
    if digest.escalate:
        print("\n[ESCALATION] review before posting:")
        for r in digest.escalation_reasons:
            print(f"  - {r}")


def main(argv: list[str] | None = None) -> int:
    import datetime as dt

    p = argparse.ArgumentParser(description="Run the agent against real GitHub users.")
    p.add_argument("--provider", default="mock", help="ollama|gemini|openai|mock")
    p.add_argument("--model", help="model id for the provider")
    p.add_argument("--user", help="run a single user instead of the default set")
    p.add_argument("--date", help="ISO date for --user (default: today)")
    args = p.parse_args(argv)

    llm = get_provider(provider=args.provider, model=args.model)
    agent = StandupAgent(llm)
    tool = GitHubTool()

    print(f"Provider: {llm.name}")
    if not os.getenv("GITHUB_TOKEN"):
        print("Note: no GITHUB_TOKEN set - using anonymous rate limit.")

    if args.user:
        targets = [(args.user, args.date or dt.date.today().isoformat())]
    else:
        today = dt.date.today().isoformat()
        targets = [(u, d or today) for u, d in DEFAULT_TARGETS]

    for user, date in targets:
        try:
            run_one(agent, tool, user, date)
        except Exception as exc:  # noqa: BLE001 - keep demo going across users
            print(f"\n[skip] {user}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

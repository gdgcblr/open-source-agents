"""CLI entrypoint for standup-digest-bot.

Examples
--------
# Fully offline, no keys, no network (deterministic mock LLM + sample data):
python main.py --test-mode

# Real run against GitHub, summarizing today for a user, using local Ollama:
python main.py --user octocat --date 2026-10-24

# Use a specific provider/model:
python main.py --user octocat --provider gemini --model gemini-2.5-flash

# Summarize from a saved activity file instead of calling GitHub:
python main.py --from-file sample_activity.json --provider mock
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001 - dotenv is optional at runtime
    pass

from standup.agent import StandupAgent
from standup.fixtures import load_activity_log
from standup.github_tool import GitHubTool
from standup.llm import get_provider
from standup.models import ActivityLog

HERE = os.path.dirname(os.path.abspath(__file__))


def _today() -> str:
    return dt.date.today().isoformat()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="standup-digest-bot",
        description="Draft a GitHub standup update grounded in real activity.",
    )
    p.add_argument("--user", help="GitHub username (defaults to $GITHUB_USERNAME)")
    p.add_argument("--date", default=_today(), help="ISO date YYYY-MM-DD (default: today)")
    p.add_argument("--provider", help="LLM provider: ollama|gemini|openai|mock")
    p.add_argument("--model", help="Model id for the chosen provider")
    p.add_argument("--from-file", help="Load activity from a JSON file instead of GitHub")
    p.add_argument(
        "--test-mode",
        action="store_true",
        help="Offline demo: deterministic mock LLM + bundled sample_activity.json",
    )
    p.add_argument("--json", action="store_true", help="Emit the full Digest as JSON")
    return p


def resolve_activity(args: argparse.Namespace) -> ActivityLog:
    """Decide where the activity comes from: fixture file or live GitHub."""
    if args.test_mode:
        return load_activity_log(os.path.join(HERE, "sample_activity.json"))
    if args.from_file:
        return load_activity_log(args.from_file)

    user = args.user or os.getenv("GITHUB_USERNAME")
    if not user:
        print(
            "error: no GitHub user. Pass --user, set GITHUB_USERNAME, "
            "or run with --test-mode.",
            file=sys.stderr,
        )
        sys.exit(2)
    tool = GitHubTool()
    return tool.fetch_day(user, args.date)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "info").upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )

    # In test mode force the mock provider so no keys/network are needed.
    provider_name = "mock" if args.test_mode else args.provider

    log = resolve_activity(args)
    llm = get_provider(provider=provider_name, model=args.model)
    agent = StandupAgent(llm)
    digest = agent.generate(log)

    if args.json:
        print(json.dumps(digest.to_dict(), indent=2))
        return 0

    # Human-readable report.
    print(f"\n=== Standup for {log.username} - {log.date} ===\n")
    print(digest.text)

    if digest.needs_confirmation:
        print("\n--- Needs your confirmation ---")
        for item in digest.needs_confirmation:
            print(f"  ? {item}")

    if digest.escalate:
        print("\n[ESCALATION] This draft should be reviewed by a human before posting:")
        for reason in digest.escalation_reasons:
            print(f"  - {reason}")
        # Non-zero-ish signal without being a hard failure, so scripts can react.
        return 3

    print("\nLooks grounded. Safe to post after a quick glance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

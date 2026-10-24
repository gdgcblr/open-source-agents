"""CLI entry point. `expiry` and `optimize --category` are fully offline;
`optimize --goal` narration and `chat` need GEMINI_API_KEY (free tier works)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from engine import CATEGORIES, expiring_points, format_expiry, format_table, rank_routes
from portfolio import PortfolioError, load_portfolio, load_rates

BASE = Path(__file__).resolve().parent


def load_inputs(args):
    rates = load_rates(args.rates)
    portfolio = load_portfolio(args.portfolio, rates)
    return portfolio, rates


def main(argv=None) -> int:
    if not os.environ.get("NO_DOTENV"):
        try:
            from dotenv import load_dotenv
            load_dotenv(BASE / ".env")
        except ImportError:
            pass

    parser = argparse.ArgumentParser(prog="card-rewards-optimizer")
    parser.add_argument("--portfolio", default=str(BASE / "examples" / "portfolio.yaml"))
    parser.add_argument("--rates", default=str(BASE / "data" / "transfer_rates.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)

    p_exp = sub.add_parser("expiry", help="points expiring soon, with best use")
    p_exp.add_argument("--horizon", type=int, default=90)

    p_opt = sub.add_parser("optimize", help="rank redemption routes for a goal")
    group = p_opt.add_mutually_exclusive_group(required=True)
    group.add_argument("--goal", help='free text, e.g. "flight to Singapore"')
    group.add_argument("--category", choices=CATEGORIES)

    sub.add_parser("chat", help="interactive grounded Q&A (needs GEMINI_API_KEY)")

    args = parser.parse_args(argv)
    try:
        portfolio, rates = load_inputs(args)
    except (PortfolioError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.command == "expiry":
        print(format_expiry(expiring_points(portfolio, rates,
                                            horizon_days=args.horizon), rates.as_of))
        return 0

    if args.command == "optimize":
        if args.category:
            print(format_table(rank_routes(portfolio, rates, args.category), rates.as_of))
            return 0
        import agent
        try:
            handled = agent.run_optimize_narration(args.goal, portfolio, rates)
        except agent.AgentError as e:
            print(f"error: {e}", file=sys.stderr)
            print("tip: `optimize --category cash|flights|hotels|shopping` works offline.",
                  file=sys.stderr)
            return 3
        if not handled:
            print("No GEMINI_API_KEY set — showing all routes unranked by goal.\n"
                  "Set a free key (https://aistudio.google.com/apikey) for goal parsing.\n")
            print(format_table(rank_routes(portfolio, rates), rates.as_of))
        return 0

    if args.command == "chat":
        import agent
        if agent.get_client() is None:
            print("chat requires GEMINI_API_KEY (free at https://aistudio.google.com/apikey)",
                  file=sys.stderr)
            return 2
        agent.run_chat(portfolio, rates)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Local CLI for OAuth, ingestion, reasoning, review and approved-only totals."""

import argparse
import asyncio
import json
from pathlib import Path

from .agent import ExpenseAgent, GeminiConfigurationError, GeminiExtractor
from .connectors import DATA_HOME, DEFAULT_QUERY, authorize_gmail, fetch_gmail, read_keep
from .ledger import Ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_HOME)
    commands = parser.add_subparsers(dest="command", required=True)
    auth = commands.add_parser("auth-gmail")
    auth.add_argument("--credentials", required=True, type=Path)
    gmail = commands.add_parser("fetch-gmail")
    gmail.add_argument("--query", default=DEFAULT_QUERY)
    gmail.add_argument("--limit", type=int, default=20)
    keep = commands.add_parser("import-keep")
    keep.add_argument("path", type=Path)
    reason = commands.add_parser("reason")
    reason.add_argument("--model", help="Gemini model ID; defaults to GEMINI_MODEL or the configured default")
    commands.add_parser("list")
    review = commands.add_parser("review")
    review.add_argument("candidate_id")
    review.add_argument("--action", required=True, choices=["approved", "rejected"])
    review.add_argument("--note", required=True)
    review.add_argument("--confirm-distinct", action="store_true")
    monthly = commands.add_parser("monthly")
    monthly.add_argument("month")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "auth-gmail":
        authorize_gmail(args.credentials, args.data_dir / "gmail-token.json")
        print("Gmail connected with read-only access.")
        return 0
    ledger = Ledger(args.data_dir / "ledger.sqlite3")
    agent = ExpenseAgent(ledger)
    try:
        if args.command == "fetch-gmail":
            result = agent.ingest(fetch_gmail(args.data_dir / "gmail-token.json", args.query, args.limit))
        elif args.command == "import-keep":
            result = agent.ingest(read_keep(args.path))
        elif args.command == "reason":
            agent.extractor = GeminiExtractor(args.model)
            result = asyncio.run(agent.reason())
        elif args.command == "list":
            result = ledger.snapshot()
        elif args.command == "review":
            ledger.review(args.candidate_id, args.action, args.note, confirm_duplicate=args.confirm_distinct)
            result = {"status": args.action}
        else:
            result = ledger.monthly(args.month)
        print(json.dumps(result, indent=2))
        return 1 if isinstance(result, dict) and result.get("errors") else 0
    except GeminiConfigurationError as error:
        parser.exit(1, f"{error}\n")
    except Exception as error:
        parser.exit(1, f"Operation failed ({type(error).__name__}). Check configuration and source access.\n")


if __name__ == "__main__":
    raise SystemExit(main())
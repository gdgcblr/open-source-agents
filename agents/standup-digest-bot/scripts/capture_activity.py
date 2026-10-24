"""Capture a real GitHub user's activity for one day into a replayable JSON file.

This turns live GitHub data into a static fixture you can:
  * replay offline (no network / no rate limits) with `main.py --from-file`,
  * check into the repo as *genuine* example data (the contribution guide asks
    for honest, real inputs/outputs rather than fabricated ones),
  * feed into the eval harness as a ground-truth activity log.

Usage
-----
    # Capture today for a user (uses $GITHUB_TOKEN if set, else public/anon):
    python scripts/capture_activity.py --user torvalds

    # Capture a specific day to a named file:
    python scripts/capture_activity.py --user torvalds --date 2026-10-04 \
        --out evals/fixtures/torvalds_2026-10-04.json

No API key is required for public accounts (subject to GitHub's anonymous rate
limit). Set GITHUB_TOKEN for higher limits or private activity.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# Make the sibling package importable when run as a script.
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

from standup.github_tool import GitHubTool  # noqa: E402


def _today() -> str:
    return dt.date.today().isoformat()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Snapshot real GitHub activity to JSON.")
    p.add_argument("--user", required=True, help="GitHub username to capture")
    p.add_argument("--date", default=_today(), help="ISO date YYYY-MM-DD (default: today)")
    p.add_argument("--out", help="Output path (default: captured_<user>_<date>.json)")
    args = p.parse_args(argv)

    out = args.out or os.path.join(
        PROJECT_ROOT, f"captured_{args.user}_{args.date}.json"
    )

    tool = GitHubTool()  # reads GITHUB_TOKEN from env if present
    log = tool.fetch_day(args.user, args.date)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(log.to_dict(), fh, indent=2)
        fh.write("\n")

    print(f"Captured {len(log.events)} event(s) for {args.user} on {args.date}")
    if log.partial:
        print("  (partial: some sources failed -> " + "; ".join(log.fetch_warnings) + ")")
    print(f"Wrote {out}")
    if not log.events:
        print("  Note: no activity found for this day. Try a different --date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

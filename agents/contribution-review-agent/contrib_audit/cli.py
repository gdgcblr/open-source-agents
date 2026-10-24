"""CLI for the contribution auditor."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .models import Verdict
from .report import render_json, render_markdown, render_text
from .rules import run_all


def _find_repo_root(start: Path) -> Path:
    """Walk up from start until we find a directory containing template/README.md."""
    current = start.resolve()
    for _ in range(20):
        if (current / "template" / "README.md").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start.resolve()


def cmd_check(args: argparse.Namespace) -> int:
    project_path = Path(args.path).resolve()

    if not project_path.exists():
        print(f"Error: path does not exist: {project_path}", file=sys.stderr)
        return 2

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = _find_repo_root(project_path)

    result = run_all(project_path, repo_root)

    fmt = args.format
    use_colour = sys.stdout.isatty() and fmt == "text"

    if fmt == "json":
        print(render_json(result))
    elif fmt == "markdown":
        print(render_markdown(result))
    else:
        print(render_text(result, use_colour=use_colour))

    v = result.verdict
    return 0 if v in (Verdict.READY, Verdict.APPROVE_WITH_NITS) else 1


def cmd_triage(args: argparse.Namespace) -> int:
    from .github_source import GitHubClient, RateLimitError, triage_pr

    token = os.getenv("GITHUB_TOKEN")
    client = GitHubClient(token=token)

    if "/" not in args.repo:
        print("Error: --repo must be OWNER/NAME", file=sys.stderr)
        return 2

    owner, repo = args.repo.split("/", 1)
    limit = args.limit

    try:
        prs = client.list_open_prs(owner, repo, limit=limit)
    except RateLimitError as e:
        print(f"\n⛔ {e}\n", file=sys.stderr)
        if not token:
            print(
                "Tip: set GITHUB_TOKEN in .env to get 5000 req/hr instead of 60.",
                file=sys.stderr,
            )
        return 1
    except Exception as e:
        print(f"Error fetching PRs: {e}", file=sys.stderr)
        return 1

    if not prs:
        print("No open PRs found.")
        return 0

    results = []
    for pr in prs:
        print(f"  Checking PR #{pr['number']}…", file=sys.stderr, end="\r")
        try:
            r = triage_pr(client, owner, repo, pr)
            results.append(r)
        except RateLimitError as e:
            print(f"\n⛔ {e}", file=sys.stderr)
            break
        except Exception as e:
            results.append({
                "pr": pr["number"],
                "author": pr.get("user", {}).get("login", "?"),
                "title": pr.get("title", "")[:40],
                "project_dir": "?",
                "verdict": "ERROR",
                "top_issues": [str(e)],
                "finding_count": 0,
            })

    # Generate per-project AI summaries if GOOGLE_API_KEY is available (stretch goal)
    has_api_key = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    summaries: dict[int, str] = {}
    if has_api_key:
        from .summaries import summarize_readmes
        pr_readmes = {r["pr"]: r["readme_excerpt"] for r in results if r.get("readme_excerpt")}
        if pr_readmes:
            print("  Generating AI summaries for PRs…", file=sys.stderr, end="\r")
            summaries = summarize_readmes(pr_readmes)

    # Print ranked table (REJECT first, then CHANGES_REQUESTED, etc.)
    _RANK = {"REJECT": 0, "CHANGES_REQUESTED": 1, "APPROVE_WITH_NITS": 2, "READY": 3}
    results.sort(key=lambda r: _RANK.get(r["verdict"], 99))

    _BADGE = {
        "REJECT": "🔴",
        "CHANGES_REQUESTED": "🟡",
        "APPROVE_WITH_NITS": "🔵",
        "READY": "🟢",
        "ERROR": "⚪",
    }

    if summaries:
        col_w = [5, 18, 25, 26, 10, 32, 50]
        header = (
            f"{'PR':<{col_w[0]}} {'Author':<{col_w[1]}} {'Project Dir':<{col_w[2]}} "
            f"{'Verdict':<{col_w[3]}} {'Findings':<{col_w[4]}} {'Top Issues':<{col_w[5]}} {'Summary'}"
        )
        print("\n" + header)
        print("─" * 170)
        for r in results:
            badge = _BADGE.get(r["verdict"], "⚪")
            verdict_str = f"{badge} {r['verdict']}"
            top = "; ".join(r.get("top_issues", []))[:30]
            summary_text = summaries.get(r["pr"], "—")
            print(
                f"#{r['pr']:<{col_w[0]-1}} {r['author']:<{col_w[1]}} {r['project_dir']:<{col_w[2]}} "
                f"{verdict_str:<{col_w[3]}} {r.get('finding_count',0):<{col_w[4]}} {top:<{col_w[5]}} {summary_text}"
            )
    else:
        col_w = [5, 18, 28, 30, 20, 40]
        header = (
            f"{'PR':<{col_w[0]}} {'Author':<{col_w[1]}} {'Project Dir':<{col_w[2]}} "
            f"{'Verdict':<{col_w[3]}} {'Findings':<{col_w[4]}} {'Top Issues'}"
        )
        print("\n" + header)
        print("─" * 120)
        for r in results:
            badge = _BADGE.get(r["verdict"], "⚪")
            verdict_str = f"{badge} {r['verdict']}"
            top = "; ".join(r.get("top_issues", []))[:50]
            print(
                f"#{r['pr']:<{col_w[0]-1}} {r['author']:<{col_w[1]}} {r['project_dir']:<{col_w[2]}} "
                f"{verdict_str:<{col_w[3]}} {r.get('finding_count',0):<{col_w[4]}} {top}"
            )
        if not has_api_key:
            print("\n💡 Note: Per-project AI summaries skipped (set GOOGLE_API_KEY in .env to enable).")

    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m contrib_audit",
        description="Contribution Review Auditor — checks PRs against repo contribution rules.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    check_p = sub.add_parser("check", help="Audit a local project folder.")
    check_p.add_argument("path", help="Path to the project folder to audit.")
    check_p.add_argument(
        "--repo-root",
        help="Explicit path to the repository root (auto-detected if omitted).",
    )
    check_p.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format (default: text).",
    )

    # triage
    triage_p = sub.add_parser("triage", help="Triage open PRs on a GitHub repo.")
    triage_p.add_argument("--repo", required=True, metavar="OWNER/NAME", help="GitHub repo.")
    triage_p.add_argument("--limit", type=int, default=20, help="Max PRs to check (default 20).")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return cmd_check(args)
    if args.command == "triage":
        return cmd_triage(args)
    parser.print_help()
    return 2

"""Command-line entry point: `python -m slop_detector <pr-ref> [options]`."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .github_client import GitHubClient, parse_pr_ref, pull_request_from_patch
from .heuristics import run_heuristics
from .models import PullRequest, Verdict
from .report import combine, to_markdown


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="slop_detector",
        description="Score a GitHub pull request for low-effort AI slop, with evidence.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("pr", nargs="?", help="owner/repo#123 or https://github.com/owner/repo/pull/123")
    src.add_argument("--patch", type=Path, help="Analyze a local `git diff` file instead of a GitHub PR")
    src.add_argument("--from-json", type=Path, help="Analyze a PR saved earlier with --save-json (offline, reproducible)")
    p.add_argument("--title", default="", help="PR title (with --patch)")
    p.add_argument("--body-file", type=Path, help="File containing the PR description (with --patch)")
    p.add_argument("--no-llm", action="store_true", help="Heuristics only; no model call at all")
    p.add_argument(
        "--provider", choices=["ollama", "gemini"], default=None,
        help="LLM backend: local Gemma via Ollama, or hosted Gemini (default: $LLM_PROVIDER or ollama)",
    )
    p.add_argument("--model", default=None, help="Model name (default: $MODEL_NAME, else gemma4:e2b-it-qat / gemini-3.5-flash)")
    p.add_argument("--threshold", type=int, default=int(os.getenv("SLOP_THRESHOLD", "60")), help="Score that flags a PR (default 60)")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.add_argument("--save-json", type=Path, help="Write the fetched PR data to this file for offline re-runs")
    p.add_argument("--post-comment", action="store_true", help="Post/update the report as a PR comment (needs GITHUB_TOKEN)")
    p.add_argument("--label", default=None, help="Add this label to the PR when it is flagged as likely slop")
    p.add_argument("--fail-on-slop", action="store_true", help="Exit with code 2 when flagged (for CI gates)")
    return p.parse_args(argv)


def _load_pr(args: argparse.Namespace, gh: GitHubClient | None) -> PullRequest:
    if args.from_json:
        return PullRequest.model_validate_json(args.from_json.read_text())
    if args.patch:
        body = args.body_file.read_text() if args.body_file else ""
        return pull_request_from_patch(args.patch.read_text(), title=args.title, body=body)
    repo, number = parse_pr_ref(args.pr)
    assert gh is not None
    return gh.fetch_pull_request(repo, number)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parse_args(argv)
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider  # read by agent.py at import time
    remote = bool(args.pr)
    if (args.post_comment or args.label) and not remote:
        print("error: --post-comment/--label need a GitHub PR reference", file=sys.stderr)
        return 1
    token = os.getenv("GITHUB_TOKEN") or None
    if (args.post_comment or args.label) and not token:
        print("error: --post-comment/--label need GITHUB_TOKEN", file=sys.stderr)
        return 1

    gh = GitHubClient(token) if remote else None
    try:
        try:
            pr = _load_pr(args, gh)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if args.save_json:
            args.save_json.write_text(pr.model_dump_json(indent=2))

        heur = run_heuristics(pr)
        llm, llm_error = None, None
        if not args.no_llm:
            from . import agent  # imported lazily: ADK is heavy and optional for --no-llm

            if args.model:
                os.environ["MODEL_NAME"] = args.model
            llm_error = agent.check_backend()
            if llm_error is None:
                print(f"Reviewing with {agent.provider()}:{agent.model_name()} ...", file=sys.stderr)
                try:
                    llm = asyncio.run(agent.review_with_llm(pr, heur))
                except Exception as e:  # report and fall back to heuristics rather than failing CI
                    first_line = (str(e).strip().splitlines() or [""])[0]
                    llm_error = f"{type(e).__name__}: {first_line[:200]}"

        report = combine(pr, heur, llm, args.threshold, llm_error)
        md = to_markdown(report)
        if args.format == "json":
            print(json.dumps(report.model_dump(mode="json", exclude={"pr": {"files", "manifests"}}), indent=2))
        else:
            print(md)

        if args.post_comment:
            url = gh.upsert_comment(pr.repo, pr.number, md)
            print(f"\nPosted report: {url}", file=sys.stderr)
        if args.label and report.verdict == Verdict.LIKELY_SLOP:
            gh.add_label(pr.repo, pr.number, args.label)
            print(f"Labeled PR with {args.label!r}", file=sys.stderr)
    finally:
        if gh:
            gh.close()

    return 2 if args.fail_on_slop and report.verdict == Verdict.LIKELY_SLOP else 0

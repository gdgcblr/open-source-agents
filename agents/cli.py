"""Command line entry point:  python -m pr_review_agent --help"""
from __future__ import annotations

import argparse
import sys

from .guardrails import GuardrailError, MAX_DIFF_BYTES, redact
from .github_client import GitHubError, fetch_pr_diff, post_comment
from .llm import LLMError, get_provider
from .models import SEVERITY_RANK
from .orchestrator import ReviewOrchestrator
from .report import to_json, to_markdown


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _load_env()
    p = argparse.ArgumentParser(prog="pr_review_agent", description="AI-assisted pull request reviewer")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--diff", help="path to a unified diff file, or '-' for stdin")
    src.add_argument("--pr", help="GitHub PR reference: owner/repo#123")
    p.add_argument("--provider", help="mock | anthropic | openai | gemini | ollama (default: $LLM_PROVIDER or mock)")
    p.add_argument("--no-llm", action="store_true", help="rules only; skip all model calls for reviews")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--post", action="store_true", help="post the review as a PR comment (needs --pr)")
    p.add_argument("--fail-on", choices=list(SEVERITY_RANK), help="exit 1 if any finding is at/above this severity")
    args = p.parse_args(argv)

    if args.post and not args.pr:
        p.error("--post requires --pr")

    try:
        if args.pr:
            diff = fetch_pr_diff(args.pr)
        elif args.diff == "-":
            diff = sys.stdin.read()
        else:
            with open(args.diff, encoding="utf-8") as fh:
                diff = fh.read()
        if len(diff.encode('utf-8')) > MAX_DIFF_BYTES:
            raise GuardrailError('Diff exceeds configured maximum size (1 MB)')
        provider = get_provider('mock' if args.no_llm else args.provider)
    except (GitHubError, LLMError, GuardrailError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        result = ReviewOrchestrator(provider, use_llm=not args.no_llm).run(diff)
    except (GuardrailError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    output = to_json(result) if args.format == "json" else to_markdown(result)
    print(redact(output))

    if args.post:
        try:
            if __import__('os').getenv('ALLOW_GITHUB_POST', '').lower() != 'true':
                raise GitHubError('Posting requires ALLOW_GITHUB_POST=true')
            print(f"\nPosted: {post_comment(args.pr, redact(to_markdown(result)))}", file=sys.stderr)
        except GitHubError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    if args.fail_on:
        limit = SEVERITY_RANK[args.fail_on]
        if any(SEVERITY_RANK[f.severity] <= limit for f in result.findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from . import __version__
from .errors import AgentError, AIUnavailableError, InvalidInputError, NotFoundError
from .github_client import MAX_LIMIT, GitHubClient, parse_repo
from .guardrails import redact
from .models import Report, ScoredIssue
from .output import render_json, render_text
from .scoring import rank, score_issue
from .sentry_client import ErrorTrackerClient, make_tracker_ref, parse_issue_id

EXAMPLES = """examples:
  python -m good_first_issue_agent --repo pallets/flask
  python -m good_first_issue_agent --repo owner/repo --label "good first issue" --limit 10
  python -m good_first_issue_agent --repo owner/repo --issue 123
  python -m good_first_issue_agent --repo owner/repo --format json
  python -m good_first_issue_agent --repo owner/repo --issue 123 --ai
  python -m good_first_issue_agent --source sentry --org my-org --project web-app
  python -m good_first_issue_agent --source glitchtip --base-url https://glitchtip.example.com --org acme --project api

Tokens and API keys are read from environment variables or .env, never from arguments.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m good_first_issue_agent",
        description=(
            "Find approachable issues in a GitHub repository (or a Sentry/GlitchTip project), "
            "explain the ranking, and suggest an investigation plan. Read-only."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", choices=["github", "sentry", "glitchtip"], default="github",
                   help="where to read issues from (default: github)")
    p.add_argument("--repo", help="GitHub repository: owner/repo or a github.com URL")
    p.add_argument("--org", help="Sentry/GlitchTip organization slug (or SENTRY_ORG / GLITCHTIP_ORG)")
    p.add_argument("--project", help="Sentry/GlitchTip project slug (or SENTRY_PROJECT / GLITCHTIP_PROJECT)")
    p.add_argument("--base-url", help="Sentry/GlitchTip URL (default https://sentry.io or https://app.glitchtip.com)")
    p.add_argument("--label", action="append", metavar="LABEL",
                   help="only issues with this GitHub label; repeat to require several")
    p.add_argument("--limit", type=int, default=20, help=f"issues to fetch and rank, 1-{MAX_LIMIT} (default 20)")
    p.add_argument("--top", type=int, default=5, help="how many ranked issues to show (default 5)")
    p.add_argument("--issue", help="analyze one issue: GitHub number or Sentry/GlitchTip issue id")
    p.add_argument("--format", choices=["text", "json"], default="text", help="output format (default text)")
    p.add_argument("--ai", action="store_true",
                   help="add a Gemini (Google ADK) explanation and plan; needs GOOGLE_API_KEY")
    p.add_argument("--allow-private-data-to-ai", action="store_true",
                   help="required with --ai for Sentry/GlitchTip: confirms masked error data may be sent to Gemini")
    p.add_argument("--model", help="Gemini model (default: GEMINI_MODEL or gemini-flash-latest)")
    p.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds, 1-60 (default 10)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _load_dotenv() -> None:
    """Load .env from the project folder if python-dotenv is installed. Existing
    environment variables win."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(here, ".env"), override=False)


def _use_os_trust_store() -> None:
    """Verify HTTPS with the operating system's certificate store (like curl and browsers do),
    so the tool works behind TLS-inspecting proxies such as Cloudflare WARP or corporate gateways.
    Falls back to the certifi bundle if truststore is not installed."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


def _env(name: str) -> str | None:
    """Read a setting; empty values and untouched .env.example placeholders count as unset."""
    value = os.environ.get(name, "").strip()
    if value.lower().startswith("your_") or value.lower().endswith("_here"):
        return None
    return value or None


def build_report(
    args: argparse.Namespace,
    *,
    session: Any = None,
    ai_runner: Callable[..., Any] | None = None,
) -> Report:
    if args.source == "github":
        report, ctx = _github_report(args, session)
    else:
        report, ctx = _tracker_report(args, session)

    if args.ai:
        _add_ai(args, report, ctx, ai_runner)
    return report


def _github_report(args: argparse.Namespace, session: Any) -> tuple[Report, dict[str, Any]]:
    if args.org or args.project or args.base_url:
        raise InvalidInputError("--org, --project and --base-url are for --source sentry/glitchtip.")
    if not args.repo:
        raise InvalidInputError("--repo is required, e.g. --repo pallets/flask")
    ref = parse_repo(args.repo)
    issue_number = args.issue if args.issue is not None else ref.issue
    if issue_number is not None:
        text = str(issue_number).lstrip("#")
        if not text.isdigit() or int(text) < 1:
            raise InvalidInputError(f"--issue must be a positive issue number (got '{issue_number}').")
        issue_number = int(text)

    client = GitHubClient(ref, token=_env("GITHUB_TOKEN"), session=session, timeout=args.timeout)
    meta = client.get_repo()
    report = Report(source="github", target=meta["full_name"], target_url=meta["html_url"])
    if meta["archived"]:
        report.warnings.append("This repository is archived (read-only); it no longer accepts contributions.")
    if meta["has_issues"] is False:
        raise NotFoundError(f"Issues are disabled for {meta['full_name']}.")

    if issue_number is not None:
        issue = client.get_issue(issue_number)
        if issue.state != "open":
            report.warnings.append(f"Issue {issue.display_id} is {issue.state}; it may already be resolved.")
        report.selected = score_issue(issue)
        report.fetched = 1
    else:
        issues, excluded = client.list_issues(labels=args.label, limit=args.limit)
        report.fetched, report.excluded_pull_requests = len(issues), excluded
        report.ranked = rank(issues)
        if report.ranked:
            report.selected = report.ranked[0]
        else:
            hint = f" with label(s) {', '.join(args.label)}" if args.label else ""
            report.warnings.append(
                f"No open issues{hint} were found in the most recent {client.max_pages} page(s) of results."
                + (" Label names must match exactly; try without --label." if args.label else "")
            )
    return report, {"github": client, "meta": meta}


def _tracker_report(args: argparse.Namespace, session: Any) -> tuple[Report, dict[str, Any]]:
    kind = args.source
    prefix = kind.upper()
    if args.repo:
        raise InvalidInputError("--repo is for --source github. Use --org and --project for error trackers.")
    if args.label:
        raise InvalidInputError("--label only applies to GitHub issues.")
    ref = make_tracker_ref(
        kind,
        args.base_url or _env(f"{prefix}_URL"),
        args.org or _env(f"{prefix}_ORG"),
        args.project or _env(f"{prefix}_PROJECT"),
    )
    client = ErrorTrackerClient(ref, token=_env(f"{prefix}_AUTH_TOKEN"), session=session, timeout=args.timeout)
    report = Report(source=kind, target=ref.full_name, target_url=ref.base_url)

    if args.issue is not None:
        issue = client.get_issue(parse_issue_id(args.issue))
        report.fetched = 1
        report.selected = _enrich_with_event(client, issue, report)
        if issue.state not in ("unresolved", ""):
            report.warnings.append(f"Issue {issue.display_id} is '{issue.state}'.")
    else:
        issues = client.list_issues(limit=args.limit)
        report.fetched = len(issues)
        report.ranked = rank(issues)
        if report.ranked:
            top = report.ranked[0]
            report.selected = _enrich_with_event(client, top.issue, report)
            report.ranked[0] = report.selected
        else:
            report.warnings.append("No unresolved issues were found for this project in the selected period.")
    return report, {"tracker": client}


def _enrich_with_event(client: ErrorTrackerClient, issue, report: Report) -> ScoredIssue:
    """Add in-app stack frames from the latest event. Failures only add a warning."""
    try:
        event = client.get_latest_event(issue.id)
    except AgentError as exc:
        report.warnings.append(f"Could not load the latest event: {exc}")
        return score_issue(issue)
    files = []
    lines = []
    for fr in event.get("frames", []):
        if fr["in_app"] and fr["file"] and fr["file"] not in files:
            files.append(fr["file"])
        lines.append(f"  {fr['file']}:{fr['line']} in {fr['function']}" + ("" if fr["in_app"] else " (library)"))
    if files:
        issue.stack_files = files[:8] + [f for f in issue.stack_files if f not in files]
    if lines:
        issue.body += "\nStack trace (innermost first):\n" + "\n".join(lines[:10])
    return score_issue(issue)


def _add_ai(args: argparse.Namespace, report: Report, ctx: dict[str, Any], ai_runner: Callable[..., Any] | None) -> None:
    if args.source != "github" and not args.allow_private_data_to_ai:
        report.warnings.append(
            "AI analysis skipped: error-tracker data is private. Add --allow-private-data-to-ai to send "
            "masked titles, messages and stack frames to Gemini."
        )
        return
    if report.selected is None:
        report.warnings.append("AI analysis skipped: there is no issue to analyze.")
        return
    if ai_runner is None:
        from .agent import run_ai_analysis as ai_runner  # lazy: ADK is optional
    model = args.model or _env("GEMINI_MODEL") or "gemini-flash-latest"
    try:
        report.ai = ai_runner(report=report, ctx=ctx, model=model)
    except AIUnavailableError as exc:
        report.warnings.append(f"AI analysis unavailable ({exc}). Showing deterministic results only.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_LIMIT}")
    if not 1 <= args.top <= MAX_LIMIT:
        parser.error(f"--top must be between 1 and {MAX_LIMIT}")
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
    _load_dotenv()
    _use_os_trust_store()

    try:
        report = build_report(args)
    except AgentError as exc:
        return _fail(args, str(exc), exc.exit_code)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # last resort: never print a traceback that could contain secrets
        msg = redact(f"{type(exc).__name__}: {exc}")[0]
        return _fail(args, f"Unexpected error: {msg}", 1)

    if args.format == "json":
        print(render_json(report, top=args.top))
    else:
        print(render_text(report, top=args.top))
    return 0


def _fail(args: argparse.Namespace, message: str, code: int) -> int:
    message = redact(message)[0]
    if args.format == "json":
        import json

        print(json.dumps({"error": message}))
    print(f"Error: {message}", file=sys.stderr)
    return code

#!/usr/bin/env python3
"""
Autonomous GitHub PR Reviewer & Triage Agent Council CLI.
Orchestrates Security, Performance, Test Synthesizer, and Self-Healing specialist agents.
"""

import argparse
import json
import os
import sys

# Load environment variables from .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pr_agent.reviewer import PRReviewerAgent
from pr_agent.github_client import fetch_pr_diff, load_diff_from_file, load_diff_from_stdin, parse_pr_target
from pr_agent.html_reporter import generate_html_dashboard
from pr_agent.terminal_ui import print_rich_report, print_healing_scorecard
from pr_agent.self_healing import SelfHealingEngine
from pr_agent.server import start_server
from pr_agent.hooks import install_git_hook
from pr_agent.exceptions import PRAgentError


def parse_args():
    parser = argparse.ArgumentParser(
        description="🏛️ Autonomous GitHub PR Reviewer & Triage Council: Multi-agent security audit, performance analysis, automated test synthesis, and self-healing patching."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pr",
        type=str,
        help="GitHub PR URL (https://github.com/owner/repo/pull/123) or slug (owner/repo#123)"
    )
    group.add_argument(
        "--diff",
        type=str,
        help="Path to local unified diff or patch file"
    )
    group.add_argument(
        "--stdin",
        action="store_true",
        help="Read diff from standard input (e.g., git diff | python main.py --stdin)"
    )
    group.add_argument(
        "--sample",
        action="store_true",
        help="Run analysis on bundled sample diff (zero configuration demonstration)"
    )
    group.add_argument(
        "--serve",
        nargs="?",
        const=8080,
        type=int,
        help="Start zero-dependency interactive Web UI server (default port: 8080)"
    )
    group.add_argument(
        "--install-hook",
        action="store_true",
        help="Install pre-push git hook to automatically audit commits before pushing"
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode using specialist rule council without external LLM API calls"
    )
    parser.add_argument(
        "--verify-healing",
        action="store_true",
        help="Verify self-healing: simulate patch application and display Before vs After scorecard"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
        help="Gemini model name to use (default: gemini-1.5-flash)"
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub Personal Access Token (for private repositories or higher rate limits)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to write the review markdown report (e.g. review_report.md)"
    )
    parser.add_argument(
        "--html",
        type=str,
        help="Path to export an interactive dark-mode HTML dashboard (e.g. dashboard.html)"
    )
    parser.add_argument(
        "--badge",
        type=str,
        help="Path to export an SVG Health Score badge (e.g. pr_health.svg)"
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically generate a remediation.patch file for detected issues"
    )
    parser.add_argument(
        "--patch-output",
        type=str,
        default="remediation.patch",
        help="Custom path for the auto-fix patch file (default: remediation.patch)"
    )
    parser.add_argument(
        "--generate-tests",
        type=str,
        help="Path to write synthesized unit & regression tests (e.g. generated_tests.py)"
    )
    parser.add_argument(
        "--comment",
        action="store_true",
        help="Post the review report directly to the GitHub PR conversation (requires GITHUB_TOKEN)"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exits with status code 1 if council verdict is BLOCKED"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output review report as structured JSON"
    )

    return parser.parse_args()


def post_github_pr_comment(pr_target: str, token: str, markdown_body: str) -> bool:
    """Post review report comment to GitHub PR conversation."""
    import requests
    parsed = parse_pr_target(pr_target)
    if not parsed:
        return False
    owner, repo, pr_number = parsed
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "open-source-ai-pr-reviewer"
    }
    resp = requests.post(url, headers=headers, json={"body": markdown_body}, timeout=20)
    return resp.status_code == 201


def main():
    args = parse_args()

    # Standalone utilities
    if args.serve:
        start_server(port=args.serve)
        return

    if args.install_hook:
        install_git_hook()
        return

    # Determine input source
    diff_text = None
    source_title = None

    if args.sample:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sample_path = os.path.join(current_dir, "samples", "sample_pr_diff.patch")
        diff_text, source_title = load_diff_from_file(sample_path)
        source_title = f"Sample PR Diff ({source_title})"
    elif args.pr:
        diff_text, source_title = fetch_pr_diff(args.pr, token=args.token)
    elif args.diff:
        diff_text, source_title = load_diff_from_file(args.diff)
    elif args.stdin:
        diff_text, source_title = load_diff_from_stdin()
    else:
        # Default fallback to sample mode
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sample_path = os.path.join(current_dir, "samples", "sample_pr_diff.patch")
        diff_text, source_title = load_diff_from_file(sample_path)
        source_title = f"Sample PR Diff ({source_title})"

    # Initialize reviewer agent
    agent = PRReviewerAgent(
        model_name=args.model,
        offline=args.offline
    )

    report = agent.analyze(diff_text, source_title)

    # Auto-fix patch generation
    if (args.auto_fix or args.patch_output != "remediation.patch") and report.remediation_patch:
        patch_path = args.patch_output
        with open(patch_path, "w", encoding="utf-8") as f:
            f.write(report.remediation_patch)
        print(f"🩹 Auto-fix patch written to: {patch_path}")

    # Synthesized tests export
    if args.generate_tests and report.generated_tests:
        with open(args.generate_tests, "w", encoding="utf-8") as f:
            for t in report.generated_tests:
                f.write(f"# --- {t.test_name} ({t.target_file}) ---\n")
                f.write(t.code + "\n\n")
        print(f"🧪 Synthesized unit tests written to: {args.generate_tests}")

    # HTML Dashboard export
    if args.html:
        html_code = generate_html_dashboard(report)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html_code)
        print(f"🌐 Interactive dashboard exported to: {args.html}")

    # SVG Health Score Badge export
    if args.badge:
        color = "#10b981" if report.verdict == "APPROVED" else ("#f59e0b" if report.verdict == "CHANGES_REQUESTED" else "#ef4444")
        svg_badge = f'''<svg xmlns="http://www.w3.org/2000/svg" width="180" height="28" viewBox="0 0 180 28">
  <rect rx="4" width="180" height="28" fill="#1e293b"/>
  <rect rx="4" x="90" width="90" height="28" fill="{color}"/>
  <text x="12" y="18" fill="#f8fafc" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="12" font-weight="700">PR HEALTH</text>
  <text x="135" y="18" fill="#ffffff" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="12" font-weight="800" text-anchor="middle">{report.health_score}/100</text>
</svg>'''
        with open(args.badge, "w", encoding="utf-8") as f:
            f.write(svg_badge)
        print(f"🛡️ Health Score SVG badge written to: {args.badge}")

    # Output to console
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_rich_report(report)

    # Self-Healing Verification Loop
    if args.verify_healing:
        parsed_diffs = agent.analyze(diff_text, source_title)
        # Parse diffs again and apply patch
        from pr_agent.diff_parser import parse_unified_diff
        orig_diffs = parse_unified_diff(diff_text)
        healed_diffs = SelfHealingEngine.apply_patch_to_diffs(orig_diffs, report.remediation_patch)

        # Re-evaluate healed diffs with the council
        sec_healed = agent.security_agent.evaluate(healed_diffs)
        perf_healed = agent.performance_agent.evaluate(healed_diffs)
        test_healed, gen_tests = agent.test_generator.evaluate(healed_diffs)

        from pr_agent.rules import calculate_triage
        from pr_agent.models import ReviewReport
        healed_triage = calculate_triage(healed_diffs, sec_healed.findings + perf_healed.findings, title=source_title)
        v2, score2, summ2, recs2 = agent.lead_architect.adjudicate(
            healed_triage,
            [sec_healed, perf_healed, test_healed],
            sec_healed.findings + perf_healed.findings
        )
        healed_report = ReviewReport(
            title=source_title,
            source=source_title,
            triage=healed_triage,
            issues=sec_healed.findings + perf_healed.findings,
            executive_summary=summ2,
            recommendations=recs2,
            verdict=v2,
            health_score=score2,
            specialist_reviews=[sec_healed, perf_healed, test_healed]
        )
        print_healing_scorecard(report, healed_report)

    # Post comment to GitHub if requested
    if args.comment and args.pr:
        token = args.token or os.environ.get("GITHUB_TOKEN")
        if token:
            success = post_github_pr_comment(args.pr, token, report.to_markdown())
            if success:
                print(f"💬 Review report successfully posted as comment to {args.pr}")
            else:
                sys.stderr.write(f"⚠️ Failed to post comment to {args.pr}. Verify GITHUB_TOKEN permissions.\n")
        else:
            sys.stderr.write("⚠️ GITHUB_TOKEN required to post comments to GitHub.\n")

    # Write markdown to output file if requested
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())
        print(f"\n📁 Report successfully saved to: {args.output}")

    # CI exit code handling
    if args.ci and report.verdict == "BLOCKED":
        sys.stderr.write(f"\n🛑 CI Check Failed: Pull request is BLOCKED by Council with Health Score {report.health_score}/100.\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except PRAgentError as err:
        sys.stderr.write(f"\n{err.format_diagnostic()}\n\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Operation cancelled by user.")
        sys.exit(0)
    except Exception as err:
        sys.stderr.write(f"\n❌ Unexpected Error: {err}\n\n")
        sys.exit(1)

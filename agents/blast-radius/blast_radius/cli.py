"""Command line interface for BlastRadius."""

import sys
import argparse
import json
from pathlib import Path

from .agent import BlastRadiusAgent
from .reporter import ImpactReporter
from .orchestrator import MultiServiceOrchestrator


def main():
    parser = argparse.ArgumentParser(
        prog="blast-radius",
        description="BlastRadius: Change Impact Analysis Agent for Java Microservices"
    )
    parser.add_argument(
        "--diff",
        "-d",
        required=True,
        help="Path to git diff file, or '-' to read from standard input."
    )
    parser.add_argument(
        "--repo",
        "-r",
        default=".",
        help="Path to the Java repository root (default: current directory)."
    )
    parser.add_argument(
        "--services-dir",
        help="Root directory containing multiple microservices for cross-service orchestration."
    )
    parser.add_argument(
        "--target-service",
        help="Name of the target microservice where the PR is raised (used with --services-dir)."
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional path to write the output Markdown impact report."
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)."
    )
    parser.add_argument(
        "--enable-llm",
        action="store_true",
        default=False,
        help="Opt-in to send diff data to Gemini API for semantic risk analysis. Requires GEMINI_API_KEY."
    )

    args = parser.parse_args()

    # Read diff content
    if args.diff == "-":
        diff_content = sys.stdin.read()
    else:
        diff_path = Path(args.diff)
        if not diff_path.exists():
            print(f"Error: Diff file not found: {args.diff}", file=sys.stderr)
            sys.exit(1)
        diff_content = diff_path.read_text(encoding="utf-8", errors="replace")

    # Multi-Service Orchestration Mode
    if args.services_dir and args.target_service:
        services_dir = Path(args.services_dir)
        if not services_dir.exists():
            print(f"Error: Services directory not found: {args.services_dir}", file=sys.stderr)
            sys.exit(1)

        orchestrator = MultiServiceOrchestrator()
        orchestrator.discover_services(str(services_dir))

        report = orchestrator.orchestrate_pr_impact(diff_content, args.target_service)
        output_text = report.to_markdown()

        if args.output:
            Path(args.output).write_text(output_text, encoding="utf-8")
            print(f"Multi-service impact report written to: {args.output}")
        else:
            print(output_text)
        return

    repo_path = Path(args.repo)
    if not repo_path.exists():
        print(f"Error: Target repository directory not found: {args.repo}", file=sys.stderr)
        sys.exit(1)

    # Execute Agent
    agent = BlastRadiusAgent(repo_path=str(repo_path), enable_llm=args.enable_llm)
    report = agent.analyze_diff(diff_content)

    if args.format == "json":
        data = {
            "target_repo": report.target_repo,
            "diff_file_count": report.diff_file_count,
            "risk": {
                "tier": report.risk.tier,
                "score": report.risk.score,
                "factors": report.risk.factors
            } if report.risk else None,
            "changed_methods": [
                {
                    "class": m.class_name,
                    "method": m.method_name,
                    "signature": m.signature,
                    "return_type": m.return_type,
                    "start_line": m.start_line,
                    "end_line": m.end_line,
                    "file": m.file_path
                }
                for m in report.changed_methods
            ],
            "callers": [
                {
                    "caller_class": c.caller_class,
                    "caller_method": c.caller_method,
                    "call_line": c.call_line,
                    "file": c.caller_file,
                    "is_test": c.is_test,
                    "snippet": c.code_snippet
                }
                for c in report.callers
            ],
            "recommended_tests": [
                {
                    "priority": t.priority,
                    "test_file": t.test_file,
                    "test_class": t.test_class,
                    "test_method": t.test_method,
                    "reason": t.reason
                }
                for t in report.recommended_tests
            ],
            "uncovered_methods": [m.fq_name for m in report.uncovered_methods],
            "limitations": report.limitations
        }
        output_text = json.dumps(data, indent=2)
    else:
        output_text = ImpactReporter.to_markdown(report)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Impact report successfully generated: {out_path}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()


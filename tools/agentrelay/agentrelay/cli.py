"""Unified Command-Line Interface for AgentRelay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from agentrelay.code_review import run_deterministic_review
from agentrelay.correlation import correlate_review_and_incident
from agentrelay.evaluator import run_eval_suite
from agentrelay.evidence import EvidenceStore
from agentrelay.guardrails import load_json, validate_report
from agentrelay.incident_investigator import run_incident_investigation
from agentrelay.model_policy import ModelPolicy


def format_report_text(report_dict: dict[str, Any], title: str = "INVESTIGATION REPORT") -> str:
    """Format an investigation report as clean, human-readable terminal text."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f" AgentRelay — {title}")
    lines.append("=" * 70)
    lines.append(f"Summary: {report_dict.get('summary', 'N/A')}\n")

    findings = report_dict.get("findings", [])
    if findings:
        lines.append(f"--- Findings ({len(findings)}) ---")
        for i, f in enumerate(findings, start=1):
            sev = f.get("severity", "info").upper()
            conf = f.get("confidence", "low")
            lines.append(f"[{i}] [{sev}] (Confidence: {conf}) {f.get('claim')}")
            lines.append(f"    Evidence: {', '.join(f.get('evidence_ids', []))}")
            lines.append(f"    Explanation: {f.get('explanation')}")
            lines.append(f"    Next Action: {f.get('recommended_next_action')}\n")
    else:
        lines.append("--- Findings: 0 detected ---\n")

    hypotheses = report_dict.get("alternative_hypotheses", [])
    if hypotheses:
        lines.append(f"--- Ranked Hypotheses ({len(hypotheses)}) ---")
        for h in hypotheses:
            lines.append(f"Rank {h.get('rank', 1)} [{h.get('likelihood', 'possible').upper()}]: {h.get('title')}")
            lines.append(f"    Supporting Evidence: {', '.join(h.get('supporting_evidence_ids', []))}")
            if h.get("missing_telemetry"):
                lines.append(f"    Missing Telemetry: {'; '.join(h.get('missing_telemetry', []))}")
            lines.append(f"    Explanation: {h.get('explanation')}\n")

    unknowns = report_dict.get("unknowns", [])
    if unknowns:
        lines.append("--- Unknowns & Boundaries ---")
        for u in unknowns:
            lines.append(f"  • {u}")
        lines.append("")

    recommendations = report_dict.get("recommendations", [])
    if recommendations:
        lines.append("--- Recommended Actions ---")
        for r in recommendations:
            lines.append(f"  → {r}")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def format_correlation_text(report_dict: dict[str, Any]) -> str:
    """Format a correlation report as human-readable terminal text."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(" AgentRelay — Cross-Workflow Correlation Report")
    lines.append("=" * 70)
    lines.append(f"Summary: {report_dict.get('summary', 'N/A')}\n")

    correlations = report_dict.get("correlations", [])
    if correlations:
        lines.append(f"--- Linked Associations ({len(correlations)}) ---")
        for i, c in enumerate(correlations, start=1):
            rel = c.get("relation_type", "unknown").upper()
            lines.append(f"[{i}] [{rel}] Review finding: '{c.get('review_claim')}'")
            lines.append(f"    Basis: {c.get('basis')}")
            lines.append(f"    Caution: {c.get('caution_note')}\n")
    else:
        lines.append("No linked associations found between review findings and incident events.\n")

    disclaimer = report_dict.get("causation_disclaimer")
    if disclaimer:
        lines.append(f"IMPORTANT: {disclaimer}\n")

    lines.append("=" * 70)
    return "\n".join(lines)


def handle_review(args: argparse.Namespace) -> int:
    """Handle 'agentrelay review' subcommand."""
    try:
        if args.diff == "-":
            diff_text = sys.stdin.read()
        else:
            diff_text = Path(args.diff).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Error reading diff file: {exc}", file=sys.stderr)
        return 2

    report, ev_store = run_deterministic_review(
        diff_text=diff_text,
        commit_id=args.commit,
        service=args.service,
    )

    if getattr(args, "semantic", False):
        policy = ModelPolicy()
        report = policy.run_semantic_code_review(
            diff_snippet=diff_text,
            deterministic_report=report,
            evidence_store=ev_store,
        )

    if args.json:
        output_payload = {
            "report": report.to_dict(),
            "evidence": ev_store.to_list(),
        }
        print(json.dumps(output_payload, indent=2))
    else:
        print(format_report_text(report.to_dict(), title="PRE-DEPLOYMENT CODE REVIEW"))

    # Return exit code 1 if critical/high findings present, 0 otherwise
    has_high_or_crit = any(f.severity in ("critical", "high") for f in report.findings)
    return 1 if has_high_or_crit else 0


def handle_investigate(args: argparse.Namespace) -> int:
    """Handle 'agentrelay investigate' subcommand."""
    try:
        incident_data = load_json(args.incident)
    except Exception as exc:
        print(f"Error reading incident file: {exc}", file=sys.stderr)
        return 2

    report, ev_store = run_incident_investigation(incident_data)

    if args.json:
        output_payload = {
            "report": report.to_dict(),
            "evidence": ev_store.to_list(),
        }
        print(json.dumps(output_payload, indent=2))
    else:
        print(format_report_text(report.to_dict(), title="INCIDENT INVESTIGATION"))

    return 0


def handle_correlate(args: argparse.Namespace) -> int:
    """Handle 'agentrelay correlate' subcommand."""
    try:
        review_data = load_json(args.review)
        incident_data = load_json(args.incident)
    except Exception as exc:
        print(f"Error loading correlation files: {exc}", file=sys.stderr)
        return 2

    review_report = review_data.get("report", review_data)
    corr_report = correlate_review_and_incident(review_report, incident_data)

    if args.json:
        print(json.dumps(corr_report.to_dict(), indent=2))
    else:
        print(format_correlation_text(corr_report.to_dict()))

    return 0


def handle_evaluate(args: argparse.Namespace) -> int:
    """Handle 'agentrelay evaluate' subcommand."""
    cases_path = Path(args.cases)
    if not cases_path.exists():
        # Fallback to default relative to script
        pkg_root = Path(__file__).resolve().parent.parent
        cases_path = pkg_root / "evals" / "test_cases.json"

    try:
        cases = load_json(cases_path)
    except Exception as exc:
        print(f"Error loading eval test cases from {cases_path}: {exc}", file=sys.stderr)
        return 2

    summary = run_eval_suite(cases)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print("=" * 70)
        print(" AgentRelay — Offline Evaluation Suite Results")
        print("=" * 70)
        print(f"Total Test Cases Evaluated:       {summary.total_cases}")
        print(f"Passed:                           {summary.passed_cases}/{summary.total_cases} ({summary.pass_rate * 100:.1f}%)")
        print(f"Mean Score:                       {summary.mean_score:.2f}")
        print(f"Evidence Citation Validity Rate:  {summary.citation_validity_rate * 100:.1f}%")
        print(f"Abstention Accuracy:              {summary.abstention_accuracy * 100:.1f}%")
        print(f"Prompt Injection Resistance:      {summary.prompt_injection_resistance_rate * 100:.1f}%")
        print(f"Suite Execution Time:             {summary.duration_ms:.1f} ms")
        print("=" * 70)

        for res in summary.case_results:
            status = "PASS" if res.passed else "FAIL"
            print(f"  [{status}] {res.case_id:<20} ({res.category}) - Score: {res.score:.2f}")
            if not res.passed and res.details:
                print(f"         Issues: {res.details}")
        print("=" * 70)

    return 0 if summary.passed_cases == summary.total_cases else 1


def handle_validate(args: argparse.Namespace) -> int:
    """Handle 'agentrelay validate' subcommand (preserving backward compatibility)."""
    try:
        evidence = load_json(args.evidence)
        report = load_json(args.report)

        if not isinstance(evidence, list):
            print("REJECTED: evidence file must contain a JSON array.")
            return 2

        errors = validate_report(report, evidence)

        if errors:
            print("REJECTED — report failed safety checks:")
            for error in errors:
                print(f"  - {error}")
            return 1

        print("PASSED — structural and evidence-reference checks passed.")
        print("Note: semantic support for each claim still requires additional evaluation.")
        return 0

    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser supporting subcommands and legacy flags."""
    parser = argparse.ArgumentParser(
        prog="agentrelay",
        description="AgentRelay — Evidence-Driven AI Engineering Investigation Platform",
    )

    # Subparsers for commands
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # 1. review
    parser_review = subparsers.add_parser("review", help="Analyze code diff for security and reliability risks")
    parser_review.add_argument("--diff", required=True, help="Path to unified diff patch file (or '-' for stdin)")
    parser_review.add_argument("--commit", default=None, help="Associated commit SHA identifier")
    parser_review.add_argument("--service", default=None, help="Affected service name")
    parser_review.add_argument("--semantic", action="store_true", help="Enable optional semantic model review (if keys configured)")
    parser_review.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # 2. investigate
    parser_investigate = subparsers.add_parser("investigate", help="Investigate production incident telemetry")
    parser_investigate.add_argument("--incident", required=True, help="Path to incident JSON data file")
    parser_investigate.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # 3. correlate
    parser_correlate = subparsers.add_parser("correlate", help="Correlate code review findings with production incident")
    parser_correlate.add_argument("--review", required=True, help="Path to review report JSON file")
    parser_correlate.add_argument("--incident", required=True, help="Path to incident data JSON file")
    parser_correlate.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # 4. evaluate
    parser_eval = subparsers.add_parser("evaluate", help="Run offline deterministic evaluation suite")
    parser_eval.add_argument("--cases", default="evals/test_cases.json", help="Path to evaluation test cases JSON")
    parser_eval.add_argument("--json", action="store_true", help="Output evaluation metrics as JSON")

    # 5. validate (legacy support)
    parser_validate = subparsers.add_parser("validate", help="Validate report structure and evidence references")
    parser_validate.add_argument("--evidence", required=True, help="Evidence JSON file")
    parser_validate.add_argument("--report", required=True, help="Report JSON file")

    # 6. dashboard
    parser_dash = subparsers.add_parser("dashboard", help="Launch interactive local web dashboard")
    parser_dash.add_argument("--port", type=int, default=8080, help="Port to bind dashboard server (default: 8080)")
    parser_dash.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser_dash.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")


    # Top-level legacy arguments (for backwards compatibility with `agentrelay --evidence ... --report ...`)
    parser.add_argument("--evidence", default=None, help="Evidence JSON file (legacy mode)")
    parser.add_argument("--report", default=None, help="Report JSON file (legacy mode)")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args_list = argv if argv is not None else sys.argv[1:]
    parser = build_parser()

    # Legacy support: if invoked with top-level --evidence and --report
    if "--evidence" in args_list and "--report" in args_list and ("validate" not in args_list):
        args = parser.parse_args(args_list)
        return handle_validate(args)

    if not args_list:
        parser.print_help()
        return 0

    args = parser.parse_args(args_list)

    if args.subcommand == "review":
        return handle_review(args)
    elif args.subcommand == "investigate":
        return handle_investigate(args)
    elif args.subcommand == "correlate":
        return handle_correlate(args)
    elif args.subcommand == "evaluate":
        return handle_evaluate(args)
    elif args.subcommand == "validate":
        return handle_validate(args)
    elif args.subcommand == "dashboard":
        from agentrelay.dashboard import run_dashboard_server
        run_dashboard_server(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

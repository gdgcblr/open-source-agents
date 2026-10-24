"""VulnPilot CLI entry point."""
import argparse
import sys
from pathlib import Path
from agent import AIAnalysisError, analyze_findings
from reporter import print_summary, save_report
from scanner import ScanError, scan_project

def build_parser():
    parser = argparse.ArgumentParser(prog="vulnpilot", description="Scan a project with Semgrep; optionally request Gemini triage.")
    parser.add_argument("target", help="Project directory to scan")
    parser.add_argument("--report", metavar="FILE", help="Save findings as a Markdown report")
    parser.add_argument("--ai", action="store_true", help="Explicitly enable optional Gemini analysis")
    parser.add_argument("--model", help="Gemini model name (only used with --ai)")
    parser.add_argument("--mock", action="store_true", help="Offline mock scan; no Semgrep or network required")
    parser.add_argument("--mock-ai", action="store_true", help="Use offline mock AI response (implies --ai)")
    return parser

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.mock_ai:
        args.ai = True
    try:
        findings = scan_project(args.target, mock=args.mock)
        ai_text = analyze_findings(findings, mock=args.mock_ai, model=args.model) if args.ai else None
        print_summary(findings)
        if ai_text:
            print("\nAI recommendations (advisory only):\n" + ai_text)
        if args.report:
            save_report(args.report, findings, ai_text)
            print(f"\nMarkdown report saved to {Path(args.report).expanduser()}")
        return 0
    except (ScanError, AIAnalysisError, OSError) as exc:
        print(f"vulnpilot: error: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

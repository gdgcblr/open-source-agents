"""Command-line entry point for Cloud Run Launch Doctor."""

import argparse
import json
import sys
from pathlib import Path

from ai_explainer import explain_findings
from launch_doctor import scan_project
from log_diagnosis import correlate_project_findings, diagnose_log_file


def build_parser():
    parser = argparse.ArgumentParser(
        description="Check a local project for common Cloud Run deployment blockers."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to inspect (default: current directory).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 when warnings are present, as well as errors.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Ask Gemini via Google ADK to explain the deterministic findings.",
    )
    parser.add_argument(
        "--model",
        default="gemini-flash-latest",
        help="Gemini model for --explain (default: gemini-flash-latest).",
    )
    parser.add_argument(
        "--explain-timeout",
        type=float,
        default=45,
        metavar="SECONDS",
        help="Maximum seconds to wait for Gemini when --explain is enabled (default: 45).",
    )
    parser.add_argument(
        "--diagnose-log",
        metavar="FILE",
        help="Diagnose a Cloud Run log file instead of scanning a project directory.",
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        help="Optionally cross-reference log diagnoses with a local project directory.",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.diagnose_log:
        try:
            findings = diagnose_log_file(args.diagnose_log)
            project_path = None
            if args.project:
                project_path = Path(args.project).expanduser().resolve()
                if not project_path.is_dir():
                    raise ValueError("Project path is not a directory: {}".format(project_path))
                project_findings = scan_project(project_path)
                findings = correlate_project_findings(findings, project_findings)
            explanation = (
                explain_findings(findings, args.model, args.explain_timeout)
                if args.explain
                else None
            )
        except (ImportError, RuntimeError, ValueError) as error:
            print("Diagnosis unavailable: {}".format(error), file=sys.stderr)
            return 2

        if args.format == "json":
            output = {"log_file": str(Path(args.diagnose_log).expanduser()), "diagnoses": findings}
            if project_path is not None:
                output["project_path"] = str(project_path)
            if explanation is not None:
                output["explanation"] = explanation
            print(json.dumps(output, indent=2))
        else:
            print("Cloud Run log diagnosis: {}".format(args.diagnose_log))
            for finding in findings:
                print(
                    "[{}] {} (confidence: {})".format(
                        finding["severity"], finding["check"], finding["confidence"]
                    )
                )
                print("  Likely cause: {}".format(finding["cause"]))
                evidence = finding["evidence"]
                if evidence:
                    print(
                        "  Evidence, line {}: {}".format(
                            evidence["line"], evidence["text"]
                        )
                    )
                print("  Next step: {}".format(finding["next_step"]))
                for project_evidence in finding.get("project_evidence", []):
                    print(
                        "  Project evidence [{}] {}: {}".format(
                            project_evidence["severity"],
                            project_evidence["check"],
                            project_evidence["message"],
                        )
                    )
            if explanation:
                print("\nGemini explanation:\n{}".format(explanation))
        return 0

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print("Error: project path is not a directory: {}".format(root), file=sys.stderr)
        return 2

    findings = scan_project(root)
    errors = sum(finding["severity"] == "ERROR" for finding in findings)
    warnings = sum(finding["severity"] == "WARNING" for finding in findings)
    explanation = None

    if args.explain:
        try:
            explanation = explain_findings(findings, args.model, args.explain_timeout)
        except (ImportError, RuntimeError, ValueError) as error:
            print("Explanation unavailable: {}".format(error), file=sys.stderr)
            return 2

    if args.format == "json":
        output = {"path": str(root), "findings": findings}
        if explanation is not None:
            output["explanation"] = explanation
        print(json.dumps(output, indent=2))
    else:
        print("Cloud Run Launch Doctor: {}".format(root))
        for finding in findings:
            print(
                "[{}] {}: {}".format(
                    finding["severity"], finding["check"], finding["message"]
                )
            )
            if finding["detail"]:
                print("  {}".format(finding["detail"]))
        if explanation is not None:
            print("\nGemini explanation:\n{}".format(explanation))
        print("\n{} error(s), {} warning(s)".format(errors, warnings))

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
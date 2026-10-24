"""Command-Line Interface for Prompt Context Linter and Formatter."""

import argparse
import json
import os
import sys

# Safe UTF-8 reconfiguration on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from linter.template_linter import PromptLinter
from linter.truncator import truncate_context, TruncationPolicy
from linter.dashboard import generate_lint_dashboard_html


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Context Linter & Formatter - Static analysis, smell detection, and budget truncation for LLM prompts."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default="examples/valid_template.txt",
        help="Path to prompt template file (default: examples/valid_template.txt)",
    )
    parser.add_argument(
        "--vars",
        "-v",
        type=str,
        default="examples/sample_variables.json",
        help="Path to JSON file containing template variable bindings",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum token budget. If prompt exceeds this limit, budget truncation is triggered.",
    )
    parser.add_argument(
        "--policy",
        type=str,
        choices=["head", "tail", "sandwich"],
        default="sandwich",
        help="Budget truncation policy ('head', 'tail', or 'sandwich')",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: treat warnings and missing variables as hard errors.",
    )
    parser.add_argument(
        "--output-html",
        "-o",
        type=str,
        default="lint_report.html",
        help="Path to output interactive HTML dashboard (default: lint_report.html)",
    )

    args = parser.parse_args()

    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.abspath(args.file)
    if not os.path.exists(file_path):
        alt = os.path.join(script_dir, args.file)
        if os.path.exists(alt):
            file_path = alt
        else:
            print(f"[Error] Template file not found: {args.file}")
            sys.exit(1)

    variables = {}
    if args.vars:
        vars_path = os.path.abspath(args.vars)
        if not os.path.exists(vars_path):
            alt_v = os.path.join(script_dir, args.vars)
            if os.path.exists(alt_v):
                vars_path = alt_v
        if os.path.exists(vars_path):
            try:
                with open(vars_path, "r", encoding="utf-8") as f:
                    variables = json.load(f)
            except Exception as e:
                print(f"[Warning] Failed to parse variables JSON: {e}")

    with open(file_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    print("=" * 70)
    print("   PROMPT CONTEXT LINTER & FORMATTER")
    print("=" * 70)
    print(f" Template Target   : {file_path}")
    print(f" Variables File    : {args.vars or 'None'}")
    print(f" Strict Mode       : {args.strict}")
    print(f" Max Token Budget  : {args.max_tokens or 'Unlimited'}")
    print("=" * 70)

    linter = PromptLinter(strict_mode=args.strict)
    report = linter.lint(
        template_str=template_content,
        variables=variables,
        template_name=os.path.basename(file_path),
    )

    print(f"\n[Linter Status] {'VALID' if report.is_valid else 'FAILED'} | Issues Found: {report.total_issues}")
    print(f"Tokens Estimate: ~{report.estimated_token_count} | Characters: {report.raw_character_count}")

    if report.issues:
        print("\nFindings:")
        for idx, issue in enumerate(report.issues, 1):
            line_info = f" (line {issue.line_number})" if issue.line_number else ""
            print(f"  {idx}. [{issue.severity.value}] {issue.rule_id}{line_info}: {issue.message}")
            if issue.suggestion:
                print(f"     Suggestion: {issue.suggestion}")

    # Truncation check
    if args.max_tokens and report.estimated_token_count > args.max_tokens:
        print(f"\n[Truncator] Prompt exceeds {args.max_tokens} tokens. Applying '{args.policy}' truncation...")
        trunc_result = truncate_context(
            report.interpolated_preview,
            max_tokens=args.max_tokens,
            policy=TruncationPolicy(args.policy),
        )
        print(f"Truncated from {trunc_result.original_characters} chars (~{trunc_result.original_estimated_tokens} tokens) to {trunc_result.final_characters} chars (~{trunc_result.final_estimated_tokens} tokens).")
        report.interpolated_preview = trunc_result.content

    # Save HTML report
    if args.output_html:
        out_path = os.path.abspath(args.output_html)
        generate_lint_dashboard_html(report, out_path)
        print(f"\n[Dashboard] Report written to: {out_path}")

    print("\n" + "=" * 70)
    if report.is_valid:
        print(" RESULT: PASSED")
        print("=" * 70)
        sys.exit(0)
    else:
        print(" RESULT: FAILED (Lint errors must be resolved)")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()

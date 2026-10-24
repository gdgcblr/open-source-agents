"""Command-Line Interface for Token Usage and Cost Calculator."""

import argparse
import os
import sys

# Safe UTF-8 reconfiguration on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from calculator.analyzer import analyze_token_costs
from calculator.dashboard import generate_cost_dashboard_html
from calculator.pricing import list_supported_models


def main():
    parser = argparse.ArgumentParser(
        description="Token Usage & Cost Calculator - Multi-provider token economics audit across Gemini, OpenAI, Anthropic, and DeepSeek."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default="examples/sample_chat.json",
        help="Path to input transcript, JSON chat history, or prompt document (default: examples/sample_chat.json)",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="gemini-2.5-flash",
        help="Primary model identifier for evaluation (default: 'gemini-2.5-flash')",
    )
    parser.add_argument(
        "--output-html",
        "-o",
        type=str,
        default="cost_report.html",
        help="Path to generate self-contained HTML analytics dashboard (default: cost_report.html)",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Display all supported model identifiers and exit",
    )

    args = parser.parse_args()

    if args.list_models:
        print("Supported Models:")
        for m in list_supported_models():
            print(f" - {m}")
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.abspath(args.file)
    if not os.path.exists(target_path):
        alt = os.path.join(script_dir, args.file)
        if os.path.exists(alt):
            target_path = alt
        else:
            print(f"[Error] File not found: {args.file}")
            sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

    report = analyze_token_costs(
        text_or_transcript=content,
        primary_model_id=args.model,
        source_label=os.path.basename(target_path),
    )

    b = report.breakdown
    p = report.primary_estimate

    print("=" * 70)
    print("   TOKEN USAGE & COST CALCULATOR")
    print("=" * 70)
    print(f" Target File       : {target_path}")
    print(f" Detected Format   : {report.source_format.upper()}")
    print(f" Primary Model     : {p.model_id} ({p.provider})")
    print(f" Total Tokens      : {b.total_tokens:,} ({b.prompt_tokens:,} in / {b.completion_tokens:,} out)")
    print(f" Total Characters  : {b.total_characters:,}")
    print(f" Primary Cost      : ${p.total_cost_usd:.6f} USD")
    print("=" * 70)

    print("\nProvider Model Pricing Comparison:")
    print(f"{'Model':<22} {'Provider':<12} {'Prompt Cost':<14} {'Comp Cost':<14} {'Total Cost':<12}")
    print("-" * 74)

    for comp in report.comparisons:
        is_p = "*" if comp.model_id == p.model_id else " "
        print(
            f"{is_p} {comp.model_id:<20} {comp.provider:<12} ${comp.prompt_cost_usd:<13.6f} ${comp.completion_cost_usd:<13.6f} ${comp.total_cost_usd:<11.6f}"
        )

    print("-" * 74)
    print(f"Best Value Tier    : {report.cheapest_model_id}")
    print(f"Max Savings        : {report.max_savings_percentage}% (${report.max_savings_usd:.6f} USD vs primary)")

    if args.output_html:
        out_path = os.path.abspath(args.output_html)
        generate_cost_dashboard_html(report, out_path)
        print(f"\n[Dashboard] Report written to: {out_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()

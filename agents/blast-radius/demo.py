#!/usr/bin/env python3
"""BlastRadius Reproducible Demo.

Executes change impact analysis on the bundled sample Java microservice
using the payment gateway logic update diff.
"""

import sys
from pathlib import Path

# Add project root to path for direct invocation
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from blast_radius.agent import BlastRadiusAgent
from blast_radius.reporter import ImpactReporter


def run_demo():
    print("=" * 70)
    print("💥 BlastRadius: Change Impact Analysis Agent — Reproducible Demo")
    print("=" * 70)

    repo_path = BASE_DIR / "fixtures" / "sample_repo"
    diff_file = BASE_DIR / "fixtures" / "changes" / "payment_logic_update.diff"
    output_file = BASE_DIR / "fixtures" / "demo_output.md"

    print(f"Target Java Microservice: {repo_path}")
    print(f"Input Git Diff:          {diff_file}")
    print("-" * 70)

    if not repo_path.exists():
        print(f"Error: Fixture repo not found at {repo_path}", file=sys.stderr)
        sys.exit(1)

    if not diff_file.exists():
        print(f"Error: Fixture diff not found at {diff_file}", file=sys.stderr)
        sys.exit(1)

    diff_content = diff_file.read_text(encoding="utf-8")
    agent = BlastRadiusAgent(repo_path=str(repo_path))

    print("Running Change Impact Analysis...")
    report = agent.analyze_diff(diff_content)

    # Use relative path in report to avoid leaking local filesystem paths
    report.target_repo = "fixtures/sample_repo"
    markdown_report = ImpactReporter.to_markdown(report)

    output_file.write_text(markdown_report, encoding="utf-8")
    print(f"✅ Analysis complete! Report written to: {output_file}\n")
    print("-" * 70)
    print(markdown_report)
    print("-" * 70)
    print("✨ Demo completed successfully with 0 errors!")


if __name__ == "__main__":
    run_demo()


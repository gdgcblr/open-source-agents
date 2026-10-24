#!/usr/bin/env python3
"""
AWS to GCP Architecture & Infrastructure Migration Agent
CLI Entrypoint
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load local environment variables if available
load_dotenv()

from migrator.parser import TerraformParser
from migrator.generator import MigrationGenerator
from migrator.agent import MigrationAgent


def main():
    parser = argparse.ArgumentParser(
        description="Migrate AWS Terraform infrastructure to idiomatic Google Cloud Platform configurations."
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default="examples/aws_serverless.tf",
        help="Path to AWS Terraform file (default: examples/aws_serverless.tf)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="output",
        help="Directory to save generated GCP Terraform and Migration Report (default: output)"
    )
    parser.add_argument(
        "-p", "--project-id",
        type=str,
        default=os.getenv("GCP_PROJECT_ID", "my-gcp-project"),
        help="Target Google Cloud Project ID (default: my-gcp-project)"
    )
    parser.add_argument(
        "-r", "--region",
        type=str,
        default=os.getenv("GCP_REGION", "us-central1"),
        help="Target Google Cloud Region (default: us-central1)"
    )
    parser.add_argument(
        "-m", "--mock",
        action="store_true",
        help="Run in offline / mock mode without making external Gemini API calls (zero-cost)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Gemini API Key (optional, defaults to GEMINI_API_KEY environment variable)"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)

    print("=" * 72)
    print("   AWS to Google Cloud Platform (GCP) Migration Agent")
    print("   Build it. Document it. Open-source it.")
    print("=" * 72)

    if not input_path.exists():
        print(f"\n[Error] Input file not found: {input_path}")
        sys.exit(1)

    print(f"\n[*] Reading AWS Infrastructure from: {input_path}")
    parser_engine = TerraformParser()
    resources = parser_engine.parse_file(str(input_path))

    with open(input_path, "r", encoding="utf-8") as f:
        raw_code = f.read()

    print(f"[*] Identified {len(resources)} AWS resource block(s):")
    for res in resources:
        print(f"    - {res.resource_type}: {res.resource_name}")

    if not resources:
        print("\n[Warning] No AWS resources detected in input file. Continuing with empty set.")

    # Initialize Agent reasoning
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    mock_mode = args.mock or not bool(api_key)

    if mock_mode:
        print("\n[*] Agent Mode: Offline / Rule Engine (Zero-Cost & Deterministic)")
    else:
        print(f"\n[*] Agent Mode: Google Gemini 2.5 Flash ({os.getenv('MODEL_NAME', 'gemini-2.5-flash')})")

    agent = MigrationAgent(
        api_key=api_key,
        model_name=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
        mock_mode=mock_mode
    )

    print("[*] Synthesizing architectural translation and security recommendations...")
    llm_insights = agent.analyze_migration(
        resources=resources,
        raw_code=raw_code,
        target_project=args.project_id,
        target_region=args.region
    )

    # Generate Terraform and Migration Report
    generator = MigrationGenerator(project_id=args.project_id, region=args.region)
    gcp_terraform = generator.generate_terraform(resources)
    migration_report = generator.generate_report(resources, llm_insights=llm_insights)

    # Save outputs
    output_dir.mkdir(parents=True, exist_ok=True)
    tf_out_file = output_dir / "main.tf"
    report_out_file = output_dir / "migration_report.md"

    with open(tf_out_file, "w", encoding="utf-8") as f:
        f.write(gcp_terraform)

    with open(report_out_file, "w", encoding="utf-8") as f:
        f.write(migration_report)

    print("\n" + "=" * 72)
    print("   Migration Completed Successfully!")
    print("=" * 72)
    print(f"[OK] GCP Terraform Configuration : {tf_out_file}")
    print(f"[OK] Architecture Migration Report: {report_out_file}")
    print("\nQuick Start to Deploy:")
    print(f"  1. Review generated files in '{output_dir}/'")
    print(f"  2. cd {output_dir}")
    print("  3. gcloud auth application-default login")
    print("  4. terraform init && terraform plan")
    print("=" * 72)


if __name__ == "__main__":
    main()

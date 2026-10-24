#!/usr/bin/env python3
"""
AWS to GCP Architecture & Infrastructure Migration Agent
Three-Agent Orchestration CLI Entrypoint (GDG DevFest Edition)
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Ensure safe UTF-8 terminal encoding on Windows consoles
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load local environment variables from script directory or root
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()

from migrator.parser import TerraformParser
from migrator.generator import MigrationGenerator
from migrator.agent import MigrationAgent
from migrator.validator import TerraformHCLValidator


def main():
    base_dir = Path(__file__).resolve().parent
    default_input = str(base_dir / "examples" / "aws_enterprise_workload.tf")
    default_output = str(base_dir / "output")

    parser = argparse.ArgumentParser(
        description="Migrate AWS Terraform infrastructure to idiomatic Google Cloud Platform configurations."
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=default_input,
        help=f"Path to AWS Terraform file (default: {default_input})"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=default_output,
        help=f"Directory to save generated GCP Terraform, Report, and Dashboard (default: {default_output})"
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
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run one-click dry-run validation (Terraform CLI or deterministic static compiler)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch interactive Gemini Architecture Fixer REPL session to dynamically refine HCL"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)

    print("=" * 76)
    print("   AWS to Google Cloud Platform Migration Agent")
    print("   Three-Agent Orchestration Engine | GDG DevFest Edition")
    print("=" * 76)

    if not input_path.exists():
        print(f"\n[Error] Input file not found: {input_path}")
        sys.exit(1)

    print(f"\n[*] Ingesting AWS Infrastructure from: {input_path}")
    parser_engine = TerraformParser()
    resources = parser_engine.parse_file(str(input_path))

    with open(input_path, "r", encoding="utf-8") as f:
        raw_code = f.read()

    print(f"[*] Detected {len(resources)} AWS resource block(s):")
    for res in resources:
        print(f"    - {res.resource_type}: {res.resource_name}")

    # Orchestrator setup
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    mock_mode = args.mock or not bool(api_key)

    agent = MigrationAgent(
        api_key=api_key,
        model_name=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
        mock_mode=mock_mode
    )

    print("\n" + "-" * 76)
    print("   Running Three-Agent Orchestration Pipeline")
    print("-" * 76)

    # 1. Agent 1
    print("[1/3] [Agent 1: Topology Parser] Mapping infrastructure dependency graph...")

    # 2. Agent 3
    print("[2/3] [Agent 3: FinOps Predictor] Calculating AWS vs GCP TCO & savings delta...")

    # 3. Agent 2
    if mock_mode:
        print("[3/3] [Agent 2: GCP Refactoring Engine] Running rule-based architecture synthesizer...")
    else:
        print("[3/3] [Agent 2: GCP Refactoring Engine] Invoking Gemini Flash reasoning loop...")

    topology_graph, finops_report, llm_insights = agent.run_pipeline(
        resources=resources,
        raw_code=raw_code,
        target_project=args.project_id,
        target_region=args.region
    )

    # Generate Terraform
    generator = MigrationGenerator(project_id=args.project_id, region=args.region)
    gcp_terraform = generator.generate_terraform(resources)

    # Save initial HCL artifact
    output_dir.mkdir(parents=True, exist_ok=True)
    tf_out_file = output_dir / "main.tf"
    report_out_file = output_dir / "migration_report.md"
    dash_out_file = output_dir / "dashboard.html"

    with open(tf_out_file, "w", encoding="utf-8") as f:
        f.write(gcp_terraform)

    # One-Click Dry Run Validation
    validator = TerraformHCLValidator()
    val_report = validator.validate(str(tf_out_file))

    if args.validate:
        print("\n" + "-" * 76)
        print("   Running Terraform HCL Syntax & Schema Validation")
        print("-" * 76)
        print(f"[*] Engine: {val_report.method}")
        print(f"[*] Status: {val_report.badge_label}")
        for chk in val_report.passed_checks:
            print(f"    [OK] {chk}")
        if not val_report.is_valid:
            print(f"[!] Validation Details: {val_report.details}")

    # Generate Markdown Report and HTML Dashboard with validation status
    migration_report = generator.generate_report(
        resources=resources,
        topology=topology_graph,
        finops=finops_report,
        llm_insights=llm_insights
    )
    dashboard_html = generator.generate_dashboard_html(
        resources=resources,
        topology=topology_graph,
        finops=finops_report,
        llm_insights=llm_insights,
        validation=val_report
    )

    with open(report_out_file, "w", encoding="utf-8") as f:
        f.write(migration_report)

    with open(dash_out_file, "w", encoding="utf-8") as f:
        f.write(dashboard_html)

    print("\n" + "=" * 76)
    print("   Migration & Analysis Completed Successfully!")
    print("=" * 76)
    print(f"[*] FinOps Summary:")
    print(f"    - Baseline AWS Cost : ${finops_report.total_aws_cost:.2f} / month")
    print(f"    - Target GCP Cost   : ${finops_report.total_gcp_cost:.2f} / month")
    print(f"    - Net Monthly Saving: ${finops_report.total_savings:.2f} / month ({finops_report.savings_percentage}% savings)")
    if hasattr(finops_report, "network_gravity"):
        ng = finops_report.network_gravity
        print(f"[*] Network Gravity Analysis:")
        print(f"    - AWS Exit Toll     : ${ng.aws_exit_toll:.2f} (500GB @ $0.09/GB egress)")
        print(f"    - GCP Ingress Toll  : $0.00 (100% Free Data Ingress)")
        print(f"    - Toll Payoff Time  : {ng.amortization_days} days via GCP savings")
    print("-" * 76)
    print(f"[OK] Production GCP Terraform HCL : {tf_out_file}")
    print(f"[OK] Executive Migration Audit    : {report_out_file}")
    print(f"[OK] Interactive Visual Dashboard : {dash_out_file}")
    print(f"[OK] Validation Status            : {val_report.badge_label}")
    print("-" * 76)
    print("Quick Start for Presentation & Deployment:")
    print(f"  1. Open '{dash_out_file}' in any browser for visual demo")
    print(f"  2. Review generated GCP Terraform in '{tf_out_file}'")
    print(f"  3. Deploy to GCP: cd {output_dir} && terraform init && terraform plan")
    print("=" * 76)

    # Interactive Gemini Live Architecture Fixer
    if args.interactive:
        print("\n" + "=" * 76)
        print("   Gemini Live Architecture Fixer (Interactive Session)")
        print("   Type architecture enhancements or 'exit' / 'quit' to finish.")
        print("   Example: 'Add read replica to Cloud SQL' or 'Enable Cloud Armor WAF'")
        print("=" * 76)
        current_hcl = gcp_terraform
        while True:
            try:
                user_instruction = input("\n[fixer] Enter instruction > ").strip()
                if not user_instruction:
                    continue
                if user_instruction.lower() in ("exit", "quit", "q"):
                    print("[*] Exiting interactive architecture session.")
                    break

                print(f"[*] Applying: '{user_instruction}'...")
                updated_hcl, summary = agent.refine_architecture(
                    current_tf=current_hcl,
                    instruction=user_instruction,
                    target_project=args.project_id,
                    target_region=args.region
                )
                current_hcl = updated_hcl

                with open(tf_out_file, "w", encoding="utf-8") as f:
                    f.write(current_hcl)

                val_updated = validator.validate(str(tf_out_file))

                updated_dash = generator.generate_dashboard_html(
                    resources=resources,
                    topology=topology_graph,
                    finops=finops_report,
                    llm_insights=llm_insights + f"\n\n### Interactive Architecture Fixer\n- **Instruction:** {user_instruction}\n- **Result:** {summary}",
                    validation=val_updated
                )
                with open(dash_out_file, "w", encoding="utf-8") as f:
                    f.write(updated_dash)

                print(f"[OK] {summary}")
                print(f"[OK] Updated '{tf_out_file}' and '{dash_out_file}' ({val_updated.badge_label})")
            except (KeyboardInterrupt, EOFError):
                print("\n[*] Exiting interactive architecture session.")
                break


if __name__ == "__main__":
    main()

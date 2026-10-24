#!/usr/bin/env python3
"""Multi-Service BlastRadius Orchestrator Demo.

Simulates a Pull Request raised on 'payment-service'.
The Orchestrator dispatches contract change queries to neighbouring microservice agents
('order-service' and 'inventory-service') to determine cross-service breaking impact.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from blast_radius.orchestrator import MultiServiceOrchestrator


def run_multi_service_demo():
    print("=" * 75)
    print("🌐 BlastRadius: Multi-Service Change Impact Orchestrator Demo")
    print("=" * 75)

    microservices_dir = BASE_DIR / "fixtures" / "microservices"
    diff_file = BASE_DIR / "fixtures" / "changes" / "payment_service_pr.diff"
    output_file = BASE_DIR / "fixtures" / "multi_service_demo_output.md"

    print(f"Ecosystem Directory:  {microservices_dir}")
    print(f"Incoming PR Diff:     {diff_file}")
    print(f"Target Microservice:  payment-service")
    print("-" * 75)

    orchestrator = MultiServiceOrchestrator()
    orchestrator.discover_services(str(microservices_dir))

    print(f"Registered Microservice Agents: {list(orchestrator.services.keys())}")
    print("-" * 75)

    diff_content = diff_file.read_text(encoding="utf-8")

    print("[Step 1: Orchestrator] Ingested PR on target service 'payment-service'...")
    print("[Step 2: Payment-Service Agent] Analyzing Git diff for modified methods...")
    print("[Step 3: Orchestrator] Broadcasting public contract changes to neighbouring service agents...")

    report = orchestrator.orchestrate_pr_impact(diff_content, "payment-service")

    for s_name, imp in report.service_impacts.items():
        if imp.is_target_service:
            print(f"  🎯 [{s_name} Agent] (Target): {imp.risk_tier} Risk — {imp.rationale[0]}")
        elif imp.is_impacted:
            print(f"  ⚠️  [{s_name} Agent] (Downstream): IMPACT DETECTED! {len(imp.direct_callers)} caller(s), {len(imp.recommended_tests)} test(s) impacted.")
        else:
            print(f"  ✅ [{s_name} Agent] (Downstream): Unaffected (zero references).")

    print(f"\n[Step 4: Orchestrator] Aggregated cross-service risk rating: {report.overall_risk.tier} ({report.overall_risk.score}/100)")
    print("-" * 75)

    md = report.to_markdown()
    output_file.write_text(md, encoding="utf-8")

    print(f"✅ Multi-Service Impact Report saved to: {output_file}\n")
    print(md)
    print("-" * 75)
    print("✨ Multi-Service Orchestration Demo completed successfully!")


if __name__ == "__main__":
    run_multi_service_demo()


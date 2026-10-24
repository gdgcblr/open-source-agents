"""CLI entrypoint for Autonomous DevOps Incident Responder."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from src.agent import GeminiLLMClient, MockLLMClient
from src.config import AgentConfig
from src.models import IncidentState
from src.orchestrator import IncidentOrchestrator
from src.simulator import ServiceSimulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous DevOps Incident Responder Agent"
    )
    parser.add_argument(
        "--scenario",
        choices=["config_drift", "dependency_down", "error_spike"],
        default="config_drift",
        help="Simulated incident fault scenario to inject (default: config_drift)",
    )
    parser.add_argument(
        "--use-gemini",
        action="store_true",
        help="Use live Gemini API via official Google Gen AI SDK (requires GEMINI_API_KEY)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve high-risk remediation actions",
    )
    return parser.parse_args()


def interactive_approval(action_name: str, arguments: dict) -> bool:
    """Prompt user for high-risk action confirmation if not auto-approved."""
    print(f"\n[APPROVAL REQUIRED] High-risk remediation action requested: '{action_name}'")
    print(f"Arguments: {arguments}")
    response = input("Approve execution on simulator? [y/N]: ").strip().lower()
    return response in ("y", "yes")


def main() -> int:
    args = parse_args()
    config = AgentConfig()

    print("=" * 70)
    print("[AGENT] Autonomous DevOps Incident Responder")
    print("=" * 70)

    # 1. Initialize deterministic simulator
    simulator = ServiceSimulator(service_name="checkout-api")

    # 2. Inject selected incident scenario
    if args.scenario == "config_drift":
        print("[SETUP] Injecting invalid configuration fault into checkout-api...")
        simulator.inject_invalid_config(
            bad_config_override={"db_pool_size": -10, "request_timeout_ms": 0},
            author="cd-deploy-pipeline",
            reason="Invalid negative database connection pool size",
        )
        incident_id = "INC-101"
        title = "Checkout API Outage - Invalid Configuration Drift"
    elif args.scenario == "dependency_down":
        print("[SETUP] Injecting unavailable dependency fault: auth_service...")
        simulator.inject_unavailable_dependency(
            dependency_name="auth_service",
            message="Connection refused: port 8081 unreachable",
        )
        incident_id = "INC-102"
        title = "Checkout API Degraded - Auth Service Unavailable"
    elif args.scenario == "error_spike":
        print("[SETUP] Injecting elevated error rate fault (worker leak)...")
        simulator.inject_elevated_error_rate(
            error_rate=0.48,
            reason="Thread pool starvation and memory leak in worker threads",
        )
        incident_id = "INC-103"
        title = "Checkout API Alert - HTTP 500 Error Rate Spike"

    # 3. Choose reasoning client
    if args.use_gemini:
        if not config.has_valid_api_key():
            print("\n[ERROR] --use-gemini requested, but GEMINI_API_KEY environment variable is not set.")
            print("Set GEMINI_API_KEY or run without --use-gemini to use the deterministic mock client.")
            return 1
        print(f"[REASONING] Using live Gemini model: {config.model_name}")
        llm_client = GeminiLLMClient(config)
    else:
        print("[REASONING] Using deterministic MockLLMClient (offline, repeatable mode)")
        llm_client = MockLLMClient()

    # 4. Approval policy
    approval_callback = (lambda action, args: True) if args.auto_approve else interactive_approval

    # 5. Initialize orchestrator and run incident response
    orchestrator = IncidentOrchestrator(
        simulator=simulator,
        llm_client=llm_client,
        config=config,
        approval_callback=approval_callback,
    )

    print(f"\n[INCIDENT DETECTED] {incident_id}: {title}")
    print("Starting autonomous investigation loop...\n")

    incident = orchestrator.run_incident_response(
        incident_id=incident_id,
        title=title,
    )

    # 6. Display outcome summary
    print("\n" + "=" * 70)
    print(f"Incident Response Completed: Status = [{incident.state.value}]")
    print("=" * 70)
    print(f"Total Iterations: {incident.iterations}")
    print(f"Total Tool Calls: {len(incident.tool_calls)}")
    print(f"Severity Level: {incident.severity.value if incident.severity else 'N/A'}")
    if incident.severity_assessment:
        print(f"Response Priority: {incident.severity_assessment.priority.value}")
        print(f"Severity Reasons: {'; '.join(incident.severity_assessment.reasons)}")
    print(f"Root Cause: {incident.root_cause or 'N/A'}")

    if incident.state == IncidentState.RESOLVED:
        print(f"Resolution Summary: {incident.resolution_summary}")
        print("Final Service Status: HEALTHY [OK]")
        return 0
    elif incident.state == IncidentState.ESCALATED:
        print(f"Escalation Reason: {incident.escalation_reason}")
        print("Incident Escalated to Human On-Call [ESCALATED]")
        return 0
    else:
        print(f"Incident Ended in State: {incident.state.value} [FAILED]")
        return 1


if __name__ == "__main__":
    sys.exit(main())

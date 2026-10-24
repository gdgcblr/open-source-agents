from typing import TypedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from langgraph.graph import StateGraph, END
from models import Finding, ScanRequest


class ScanState(TypedDict):
    diff: str
    repo_name: str
    secrets_findings: list[Finding]
    injection_findings: list[Finding]
    supply_chain_findings: list[Finding]
    all_findings: list[Finding]


def _run_secrets(state: ScanState) -> dict:
    from agents.secrets_agent import run
    return {"secrets_findings": run(state["diff"])}


def _run_injection(state: ScanState) -> dict:
    from agents.prompt_injection_agent import run
    return {"injection_findings": run(state["diff"])}


def _run_supply_chain(state: ScanState) -> dict:
    from agents.supply_chain_agent import run
    return {"supply_chain_findings": run(state["diff"])}


def _aggregate(state: ScanState) -> dict:
    all_findings = (
        state.get("secrets_findings", [])
        + state.get("injection_findings", [])
        + state.get("supply_chain_findings", [])
    )
    # Sort by severity: CRITICAL > HIGH > MEDIUM > LOW
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_findings.sort(key=lambda f: order.get(f.severity.value, 4))
    return {"all_findings": all_findings}


def build_graph() -> StateGraph:
    graph = StateGraph(ScanState)

    graph.add_node("secrets", _run_secrets)
    graph.add_node("injection", _run_injection)
    graph.add_node("supply_chain", _run_supply_chain)
    graph.add_node("aggregate", _aggregate)

    graph.set_entry_point("secrets")

    # Run all three agents then aggregate
    graph.add_edge("secrets", "aggregate")
    graph.add_edge("injection", "aggregate")
    graph.add_edge("supply_chain", "aggregate")
    graph.add_edge("aggregate", END)

    return graph


def run_parallel_scan(request: ScanRequest) -> list[Finding]:
    """Run all three agents in parallel using ThreadPoolExecutor, then aggregate."""
    from agents.secrets_agent import run as run_secrets
    from agents.prompt_injection_agent import run as run_injection
    from agents.supply_chain_agent import run as run_supply_chain

    all_findings: list[Finding] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_secrets, request.diff): "secrets",
            executor.submit(run_injection, request.diff): "injection",
            executor.submit(run_supply_chain, request.diff): "supply_chain",
        }
        for future in as_completed(futures):
            try:
                all_findings.extend(future.result())
            except Exception as e:
                print(f"Agent {futures[future]} failed: {e}")

    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_findings.sort(key=lambda f: order.get(f.severity.value, 4))
    return all_findings

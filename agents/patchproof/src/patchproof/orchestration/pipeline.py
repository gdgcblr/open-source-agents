"""LangGraph and multi-agent verification orchestrator for PatchProof."""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from patchproof.agents.adjudicator import EvidenceAdjudicatorAgent
from patchproof.agents.adversarial_reviewer import AdversarialReviewerAgent
from patchproof.agents.base import (
    AdjudicatorOutput,
    AdversarialReviewerOutput,
    ChangeInvestigatorOutput,
    IntentAnalystOutput,
    TestCoverageOutput,
    VerificationAgentOutput,
)
from patchproof.agents.change_investigator import ChangeInvestigatorAgent
from patchproof.agents.intent_analyst import IntentAnalystAgent
from patchproof.agents.test_coverage import TestCoverageAgent
from patchproof.agents.verification_agent import VerificationAgent
from patchproof.config import PatchProofConfig
from patchproof.core.enums import (
    AgentStatus,
    ModelMode,
    RequirementStatus,
    SourceKind,
    Verdict,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import (
    SCHEMA_VERSION,
    AgentRun,
    ChangeMap,
    CheckRequest,
    RunEvent,
    RunInput,
    VerificationReport,
    utc_now_iso,
)
from patchproof.core.validator import assert_valid_report
from patchproof.ingestion.fixture_loader import load_fixture_snapshot
from patchproof.ingestion.github_loader import load_github_pr_snapshot
from patchproof.ingestion.snapshot import ContextSnapshot
from patchproof.providers.base import BudgetedLLMProvider, LLMProvider
from patchproof.reporting.composer import ReportComposer

GRAPH_NODE_ORDER: tuple[str, ...] = (
    "validate_input",
    "ingest_context",
    "extract_requirements",
    "map_changes",
    "parallel_coverage_and_adversarial",
    "policy_review_test_plan",
    "execute_checks",
    "adjudicate",
    "validate_report",
)


class VerificationGraphState(TypedDict, total=False):
    """Serializable LangGraph state dictionary for a PatchProof verification workflow."""

    run_id: str
    run_input: RunInput
    snapshot: ContextSnapshot
    intent_out: IntentAnalystOutput
    change_out: ChangeInvestigatorOutput
    coverage_out: TestCoverageOutput
    adversarial_out: AdversarialReviewerOutput
    combined_check_requests: list[CheckRequest]
    verification_out: VerificationAgentOutput
    adjudicator_out: AdjudicatorOutput
    agent_runs: list[AgentRun]
    events: list[RunEvent]
    budget_counters: dict[str, int]
    workflow_status: str
    report: VerificationReport


class PatchProofOrchestrator:
    """Coordinates the multi-agent verification workflow via a compiled LangGraph StateGraph."""

    def __init__(
        self,
        config: PatchProofConfig | None = None,
        provider: LLMProvider | None = None,
        intent_agent: IntentAnalystAgent | None = None,
        change_agent: ChangeInvestigatorAgent | None = None,
        coverage_agent: TestCoverageAgent | None = None,
        adversarial_agent: AdversarialReviewerAgent | None = None,
        verification_agent: VerificationAgent | None = None,
        adjudicator_agent: EvidenceAdjudicatorAgent | None = None,
        composer: ReportComposer | None = None,
        http_client: Any | None = None,
    ) -> None:
        self.config = config or PatchProofConfig.from_env()
        self.provider = provider
        self.http_client = http_client
        self.intent_agent = intent_agent or IntentAnalystAgent(provider=provider)
        self.change_agent = change_agent or ChangeInvestigatorAgent(provider=provider)
        self.coverage_agent = coverage_agent or TestCoverageAgent(provider=provider)
        self.adversarial_agent = adversarial_agent or AdversarialReviewerAgent(provider=provider)
        self.verification_agent = verification_agent or VerificationAgent(config=self.config)
        self.adjudicator_agent = adjudicator_agent or EvidenceAdjudicatorAgent()
        self.composer = composer or ReportComposer()

    def build_graph(self, ledger: EvidenceLedger) -> Any:
        """Build and compile the explicit LangGraph StateGraph for a verification run."""
        budget_provider: BudgetedLLMProvider | None = None
        if self.provider is not None and self.provider.name != "none":
            budget_provider = BudgetedLLMProvider(
                self.provider,
                max_model_calls=self.config.max_model_calls,
                max_retries_per_agent=self.config.max_retries_per_agent,
            )

        def _append_event(
            events: list[RunEvent],
            run_id: str,
            component: str,
            event_type: str,
            status: str,
            duration_ms: int | None = None,
            details: dict[str, str | int | float | bool | None] | None = None,
        ) -> list[RunEvent]:
            updated = list(events)
            updated.append(
                RunEvent(
                    event_id=f"EV-{len(updated) + 1:03d}",
                    run_id=run_id,
                    timestamp=utc_now_iso(),
                    component=component,
                    event_type=event_type,
                    status=status,
                    duration_ms=duration_ms,
                    details=dict(details or {}),
                )
            )
            return updated

        def _configure_agent_providers(active_mode: ModelMode) -> None:
            active_prov: LLMProvider | None = (
                budget_provider
                if (active_mode == ModelMode.PROVIDER or budget_provider is not None)
                else None
            )
            for agent in (
                self.intent_agent,
                self.change_agent,
                self.coverage_agent,
                self.adversarial_agent,
            ):
                if hasattr(agent, "_provider") and budget_provider is not None:
                    agent._provider = active_prov

        def validate_input_node(state: VerificationGraphState) -> VerificationGraphState:
            run_input = RunInput.model_validate(state["run_input"].model_dump())
            target_ref = (
                run_input.fixture_id
                or run_input.pull_request_url
                or run_input.local_path
                or "unknown"
            )
            id_seed = f"{run_input.source.value}:{target_ref}:{run_input.model_mode.value}"
            run_id = f"run_{hashlib.sha256(id_seed.encode('utf-8')).hexdigest()[:12]}"
            _configure_agent_providers(run_input.model_mode)

            events = _append_event([], run_id, "orchestrator", "run_created", "STARTED")
            events = _append_event(
                events,
                run_id,
                "orchestrator",
                "input_validated",
                "SUCCEEDED",
                details={
                    "source": run_input.source.value,
                    "execution_mode": run_input.execution_mode.value,
                    "model_mode": run_input.model_mode.value,
                },
            )
            return {
                "run_id": run_id,
                "run_input": run_input,
                "events": events,
                "agent_runs": [],
                "budget_counters": {
                    "model_calls": 0,
                    "retries": 0,
                    "max_model_calls": self.config.max_model_calls,
                },
                "workflow_status": "INPUT_VALIDATED",
            }

        def ingest_context_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            run_input = state["run_input"]
            fetch_start = time.perf_counter()
            if run_input.source == SourceKind.FIXTURE:
                assert run_input.fixture_id is not None
                snapshot = load_fixture_snapshot(
                    fixture_id=run_input.fixture_id,
                    config=self.config,
                    ledger=ledger,
                )
            elif run_input.source == SourceKind.GITHUB:
                assert run_input.pull_request_url is not None
                snapshot = load_github_pr_snapshot(
                    pull_request_url=run_input.pull_request_url,
                    config=self.config,
                    ledger=ledger,
                    http_client=self.http_client,
                )
            else:
                raise ValueError(
                    f"Source kind '{run_input.source.value}' is not yet enabled"
                )
            fetch_ms = int((time.perf_counter() - fetch_start) * 1000)
            events = _append_event(
                state["events"],
                run_id,
                "ingestion",
                "source_fetch_completed",
                "SUCCEEDED",
                duration_ms=fetch_ms,
                details={"snapshot_hash": snapshot.source_ref.snapshot_hash},
            )
            return {
                "snapshot": snapshot,
                "events": events,
                "workflow_status": "CONTEXT_INGESTED",
            }

        def extract_requirements_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            snapshot = state["snapshot"]
            events = _append_event(
                state["events"], run_id, self.intent_agent.name, "agent_started", "STARTED"
            )
            agent_runs = list(state["agent_runs"])
            try:
                raw = self.intent_agent.run(snapshot, ledger)
                intent_out = IntentAnalystOutput.model_validate(
                    raw.model_dump() if hasattr(raw, "model_dump") else raw
                )
                agent_runs.append(
                    intent_out.to_agent_run(
                        payload={"requirement_count": len(intent_out.requirements)}
                    )
                )
                events = _append_event(
                    events,
                    run_id,
                    self.intent_agent.name,
                    "agent_completed",
                    intent_out.status.value,
                    duration_ms=intent_out.duration_ms,
                )
            except Exception as exc:
                intent_out = IntentAnalystOutput(
                    agent_name=self.intent_agent.name,
                    schema_version=SCHEMA_VERSION,
                    status=AgentStatus.FAILED,
                    summary=f"Intent Analyst failed: {exc}",
                    warnings=[f"Intent Analyst error: {exc}"],
                    requirements=[],
                    ambiguity_questions=["Intent extraction failed; manual review required."],
                )
                agent_runs.append(intent_out.to_agent_run())
                events = _append_event(
                    events, run_id, self.intent_agent.name, "agent_failed", "FAILED"
                )
            return {
                "intent_out": intent_out,
                "agent_runs": agent_runs,
                "events": events,
                "workflow_status": "REQUIREMENTS_EXTRACTED",
            }

        def map_changes_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            snapshot = state["snapshot"]
            intent_out = state["intent_out"]
            events = _append_event(
                state["events"], run_id, self.change_agent.name, "agent_started", "STARTED"
            )
            agent_runs = list(state["agent_runs"])
            try:
                raw = self.change_agent.run(snapshot, intent_out.requirements, ledger)
                change_out = ChangeInvestigatorOutput.model_validate(
                    raw.model_dump() if hasattr(raw, "model_dump") else raw
                )
                agent_runs.append(
                    change_out.to_agent_run(
                        payload={"changed_files": change_out.change_map.changed_files}
                    )
                )
                events = _append_event(
                    events,
                    run_id,
                    self.change_agent.name,
                    "agent_completed",
                    change_out.status.value,
                    duration_ms=change_out.duration_ms,
                )
            except Exception as exc:
                change_out = ChangeInvestigatorOutput(
                    agent_name=self.change_agent.name,
                    schema_version=SCHEMA_VERSION,
                    status=AgentStatus.FAILED,
                    summary=f"Change Investigator failed: {exc}",
                    warnings=[f"Change Investigator error: {exc}"],
                    change_map=ChangeMap(),
                )
                agent_runs.append(change_out.to_agent_run())
                events = _append_event(
                    events, run_id, self.change_agent.name, "agent_failed", "FAILED"
                )
            return {
                "change_out": change_out,
                "agent_runs": agent_runs,
                "events": events,
                "workflow_status": "CHANGES_MAPPED",
            }

        def parallel_analysis_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            snapshot = state["snapshot"]
            intent_out = state["intent_out"]
            change_out = state["change_out"]
            events = _append_event(
                state["events"], run_id, self.coverage_agent.name, "agent_started", "STARTED"
            )
            events = _append_event(
                events, run_id, self.adversarial_agent.name, "agent_started", "STARTED"
            )
            agent_runs = list(state["agent_runs"])

            def _run_coverage() -> TestCoverageOutput:
                raw = self.coverage_agent.run(
                    snapshot, intent_out.requirements, change_out.change_map, ledger
                )
                return TestCoverageOutput.model_validate(
                    raw.model_dump() if hasattr(raw, "model_dump") else raw
                )

            def _run_adversarial() -> AdversarialReviewerOutput:
                raw = self.adversarial_agent.run(
                    snapshot, intent_out.requirements, change_out.change_map, ledger
                )
                return AdversarialReviewerOutput.model_validate(
                    raw.model_dump() if hasattr(raw, "model_dump") else raw
                )

            workers = min(2, self.config.max_agent_parallelism)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                cov_future = pool.submit(_run_coverage)
                adv_future = pool.submit(_run_adversarial)

                try:
                    coverage_out = cov_future.result(timeout=self.config.max_run_seconds)
                    agent_runs.append(
                        coverage_out.to_agent_run(
                            payload={"test_count": len(coverage_out.test_inventory)}
                        )
                    )
                    events = _append_event(
                        events,
                        run_id,
                        self.coverage_agent.name,
                        "agent_completed",
                        coverage_out.status.value,
                        duration_ms=coverage_out.duration_ms,
                    )
                except Exception as exc:
                    coverage_out = TestCoverageOutput(
                        agent_name=self.coverage_agent.name,
                        schema_version=SCHEMA_VERSION,
                        status=AgentStatus.FAILED,
                        summary=f"Test & Coverage Agent failed: {exc}",
                        warnings=[f"Test & Coverage Agent error: {exc}"],
                    )
                    agent_runs.append(coverage_out.to_agent_run())
                    events = _append_event(
                        events, run_id, self.coverage_agent.name, "agent_failed", "FAILED"
                    )

                try:
                    adversarial_out = adv_future.result(timeout=self.config.max_run_seconds)
                    agent_runs.append(
                        adversarial_out.to_agent_run(
                            payload={"hypothesis_count": len(adversarial_out.hypotheses)}
                        )
                    )
                    events = _append_event(
                        events,
                        run_id,
                        self.adversarial_agent.name,
                        "agent_completed",
                        adversarial_out.status.value,
                        duration_ms=adversarial_out.duration_ms,
                    )
                except Exception as exc:
                    adversarial_out = AdversarialReviewerOutput(
                        agent_name=self.adversarial_agent.name,
                        schema_version=SCHEMA_VERSION,
                        status=AgentStatus.FAILED,
                        summary=f"Adversarial Reviewer failed: {exc}",
                        warnings=[f"Adversarial Reviewer error: {exc}"],
                    )
                    agent_runs.append(adversarial_out.to_agent_run())
                    events = _append_event(
                        events, run_id, self.adversarial_agent.name, "agent_failed", "FAILED"
                    )

            return {
                "coverage_out": coverage_out,
                "adversarial_out": adversarial_out,
                "agent_runs": agent_runs,
                "events": events,
                "workflow_status": "PARALLEL_ANALYSIS_COMPLETED",
            }

        def policy_review_test_plan_node(state: VerificationGraphState) -> VerificationGraphState:
            coverage_out = state["coverage_out"]
            adversarial_out = state["adversarial_out"]
            combined_requests = list(coverage_out.check_requests) + list(
                adversarial_out.targeted_check_requests
            )
            return {
                "combined_check_requests": combined_requests,
                "workflow_status": "TEST_PLAN_REVIEWED",
            }

        def execute_checks_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            run_input = state["run_input"]
            snapshot = state["snapshot"]
            combined_requests = state["combined_check_requests"]
            events = _append_event(
                state["events"], run_id, self.verification_agent.name, "agent_started", "STARTED"
            )
            agent_runs = list(state["agent_runs"])
            try:
                raw = self.verification_agent.run(
                    snapshot=snapshot,
                    check_requests=combined_requests,
                    execution_mode=run_input.execution_mode,
                    ledger=ledger,
                )
                verification_out = VerificationAgentOutput.model_validate(
                    raw.model_dump() if hasattr(raw, "model_dump") else raw
                )
                agent_runs.append(
                    verification_out.to_agent_run(
                        payload={"check_count": len(verification_out.check_results)}
                    )
                )
                events = _append_event(
                    events,
                    run_id,
                    self.verification_agent.name,
                    "agent_completed",
                    verification_out.status.value,
                    duration_ms=verification_out.duration_ms,
                )
            except Exception as exc:
                verification_out = VerificationAgentOutput(
                    agent_name=self.verification_agent.name,
                    schema_version=SCHEMA_VERSION,
                    status=AgentStatus.FAILED,
                    summary=f"Verification Agent failed: {exc}",
                    warnings=[f"Verification Agent error: {exc}"],
                    check_results=[],
                )
                agent_runs.append(verification_out.to_agent_run())
                events = _append_event(
                    events, run_id, self.verification_agent.name, "agent_failed", "FAILED"
                )
            return {
                "verification_out": verification_out,
                "agent_runs": agent_runs,
                "events": events,
                "workflow_status": "CHECKS_EXECUTED",
            }

        def adjudicate_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            snapshot = state["snapshot"]
            intent_out = state["intent_out"]
            change_out = state["change_out"]
            coverage_out = state["coverage_out"]
            adversarial_out = state["adversarial_out"]
            verification_out = state["verification_out"]

            events = _append_event(
                state["events"], run_id, self.adjudicator_agent.name, "agent_started", "STARTED"
            )
            agent_runs = list(state["agent_runs"])

            adjudicator_out = self.adjudicator_agent.run(
                snapshot=snapshot,
                intent_output=intent_out,
                change_output=change_out,
                coverage_output=coverage_out,
                adversarial_output=adversarial_out,
                verification_output=verification_out,
                ledger=ledger,
            )

            failed_agents = [a.agent_name for a in agent_runs if a.status == AgentStatus.FAILED]
            limitations = list(adjudicator_out.limitations)
            verdict = adjudicator_out.verdict
            if failed_agents:
                limitations.append(
                    f"Partial run: upstream agent(s) failed ({', '.join(failed_agents)})."
                )
                if verdict == Verdict.READY_FOR_HUMAN_REVIEW:
                    verdict = Verdict.INCONCLUSIVE

            agent_runs.append(
                adjudicator_out.to_agent_run(payload={"verdict": verdict.value})
            )
            events = _append_event(
                events,
                run_id,
                self.adjudicator_agent.name,
                "adjudication_completed",
                adjudicator_out.status.value,
                duration_ms=adjudicator_out.duration_ms,
                details={"verdict": verdict.value},
            )

            satisfied_cnt = sum(
                1
                for r in adjudicator_out.requirements
                if r.status == RequirementStatus.SATISFIED
            )
            violated_cnt = sum(
                1
                for r in adjudicator_out.requirements
                if r.status == RequirementStatus.VIOLATED
            )
            unverified_cnt = sum(
                1
                for r in adjudicator_out.requirements
                if r.status in {RequirementStatus.UNVERIFIED, RequirementStatus.AMBIGUOUS}
            )
            exec_summary = (
                f"Verdict: {verdict.value}. Evaluated {len(adjudicator_out.requirements)} "
                f"requirement(s) ({satisfied_cnt} SATISFIED, {violated_cnt} VIOLATED, "
                f"{unverified_cnt} UNVERIFIED/AMBIGUOUS) with {len(ledger)} recorded "
                "evidence item(s)."
            )

            report = VerificationReport(
                schema_version=SCHEMA_VERSION,
                run_id=run_id,
                created_at=utc_now_iso(),
                source=snapshot.source_ref,
                verdict=verdict,
                summary=exec_summary,
                requirements=adjudicator_out.requirements,
                findings=adjudicator_out.findings,
                checks=verification_out.check_results,
                agent_runs=agent_runs,
                evidence=ledger.items(),
                traceability=adjudicator_out.traceability,
                test_proposals=coverage_out.test_proposals,
                limitations=limitations,
                open_questions=adjudicator_out.open_questions,
                events=events,
            )

            budget_counters = dict(state.get("budget_counters") or {})
            if budget_provider is not None:
                budget_counters["model_calls"] = budget_provider.call_count
                budget_counters["retries"] = budget_provider.retry_count

            return {
                "adjudicator_out": adjudicator_out,
                "agent_runs": agent_runs,
                "events": events,
                "budget_counters": budget_counters,
                "report": report,
                "workflow_status": "ADJUDICATED",
            }

        def validate_report_node(state: VerificationGraphState) -> VerificationGraphState:
            run_id = state["run_id"]
            report = state["report"]
            assert_valid_report(report)
            events = _append_event(
                state["events"], run_id, "validator", "report_validation_passed", "SUCCEEDED"
            )
            report.events = list(events)
            return {
                "events": events,
                "report": report,
                "workflow_status": "COMPLETED",
            }

        workflow = StateGraph(VerificationGraphState)
        workflow.add_node("validate_input", validate_input_node)
        workflow.add_node("ingest_context", ingest_context_node)
        workflow.add_node("extract_requirements", extract_requirements_node)
        workflow.add_node("map_changes", map_changes_node)
        workflow.add_node("parallel_coverage_and_adversarial", parallel_analysis_node)
        workflow.add_node("policy_review_test_plan", policy_review_test_plan_node)
        workflow.add_node("execute_checks", execute_checks_node)
        workflow.add_node("adjudicate", adjudicate_node)
        workflow.add_node("validate_report", validate_report_node)

        workflow.add_edge(START, "validate_input")
        for idx in range(len(GRAPH_NODE_ORDER) - 1):
            workflow.add_edge(GRAPH_NODE_ORDER[idx], GRAPH_NODE_ORDER[idx + 1])
        workflow.add_edge("validate_report", END)

        return workflow.compile()

    def execute(self, run_input: RunInput) -> VerificationReport:
        """Execute a full end-to-end verification run through the compiled LangGraph workflow."""
        ledger = EvidenceLedger(max_excerpt_bytes=self.config.max_excerpt_bytes)
        compiled_graph = self.build_graph(ledger)
        final_state: VerificationGraphState = compiled_graph.invoke({"run_input": run_input})
        return final_state["report"]


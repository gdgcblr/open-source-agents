"""End-to-end integration and CLI tests for the offline deterministic vertical slice."""

from __future__ import annotations

import json
from pathlib import Path

from patchproof.agents.adversarial_reviewer import AdversarialReviewerAgent
from patchproof.agents.base import AdversarialReviewerOutput
from patchproof.cli import main as cli_main
from patchproof.config import PatchProofConfig
from patchproof.core.enums import (
    AgentStatus,
    CheckStatus,
    FindingCategory,
    FindingStatus,
    RequirementStatus,
    SourceKind,
    Verdict,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import ChangeMap, Requirement, RunInput, VerificationReport
from patchproof.core.redaction import REDACTION_PLACEHOLDER
from patchproof.core.validator import assert_valid_report
from patchproof.ingestion.snapshot import ContextSnapshot
from patchproof.orchestration.pipeline import GRAPH_NODE_ORDER, PatchProofOrchestrator
from patchproof.providers.base import (
    BudgetedLLMProvider,
    DeterministicFakeLLMProvider,
    ProviderBudgetExceededError,
)
from patchproof.reporting.composer import ReportComposer


def test_end_to_end_retry_limit_bug_detects_seeded_defect() -> None:
    orchestrator = PatchProofOrchestrator()
    report = orchestrator.execute(
        RunInput(source=SourceKind.FIXTURE, fixture_id="retry-limit-bug")
    )

    assert_valid_report(report)
    assert report.verdict == Verdict.CHANGES_REQUESTED
    assert report.source.synthetic is True

    req_by_id = {r.requirement_id: r for r in report.requirements}
    assert "R-001" in req_by_id
    assert req_by_id["R-001"].status == RequirementStatus.VIOLATED
    assert req_by_id["R-002"].status == RequirementStatus.SATISFIED
    assert req_by_id["R-003"].status == RequirementStatus.SATISFIED

    check_by_id = {c.check_id: c for c in report.checks}
    assert check_by_id["C-001"].status == CheckStatus.FAILED
    assert check_by_id["C-001"].exit_code == 1
    assert len(check_by_id["C-001"].evidence_ids) == 1

    assert check_by_id["C-002"].status == CheckStatus.NOT_RUN
    assert check_by_id["C-002"].exit_code is None

    confirmed_defects = [
        f
        for f in report.findings
        if f.status == FindingStatus.CONFIRMED
        and f.category == FindingCategory.FUNCTIONAL_DEFECT
    ]
    assert len(confirmed_defects) == 1
    assert "R-001" in confirmed_defects[0].requirement_ids
    assert len(confirmed_defects[0].evidence_ids) >= 2

    test_gaps = [f for f in report.findings if f.category == FindingCategory.TEST_GAP]
    assert len(test_gaps) >= 1
    assert any(ev.event_type == "report_validation_passed" for ev in report.events)


def test_end_to_end_clean_control_has_no_confirmed_defects() -> None:
    orchestrator = PatchProofOrchestrator()
    report = orchestrator.execute(
        RunInput(source=SourceKind.FIXTURE, fixture_id="clean-retry-implementation")
    )

    assert_valid_report(report)
    assert report.verdict == Verdict.READY_FOR_HUMAN_REVIEW

    for req in report.requirements:
        assert req.status == RequirementStatus.SATISFIED

    confirmed_defects = [
        f
        for f in report.findings
        if f.status == FindingStatus.CONFIRMED
        and f.category in {FindingCategory.FUNCTIONAL_DEFECT, FindingCategory.REQUIREMENT_GAP}
    ]
    assert confirmed_defects == []

    check_by_id = {c.check_id: c for c in report.checks}
    assert check_by_id["C-001"].status == CheckStatus.PASSED
    assert check_by_id["C-001"].exit_code == 0

    for finding in report.findings:
        assert finding.status == FindingStatus.HYPOTHESIS


def test_prompt_injection_fixture_preserves_policy_and_redacts_secrets() -> None:
    orchestrator = PatchProofOrchestrator()
    report = orchestrator.execute(
        RunInput(source=SourceKind.FIXTURE, fixture_id="prompt-injection-issue")
    )

    assert_valid_report(report)
    assert report.verdict == Verdict.CHANGES_REQUESTED
    assert len(report.requirements) == 1
    assert report.requirements[0].status == RequirementStatus.VIOLATED

    full_json = ReportComposer().render_json(report)
    assert "ghp_1234567890" not in full_json
    assert "sk-proj-ABCDEF" not in full_json
    assert REDACTION_PLACEHOLDER in full_json
    assert any(ev.redacted for ev in report.evidence)


def test_optional_agent_failure_degrades_gracefully() -> None:
    class FailingAdversarialAgent(AdversarialReviewerAgent):
        def run(
            self,
            snapshot: ContextSnapshot,
            requirements: list[Requirement],
            change_map: ChangeMap,
            ledger: EvidenceLedger,
        ) -> AdversarialReviewerOutput:
            raise RuntimeError("Simulated provider timeout in adversarial reviewer")

    orchestrator = PatchProofOrchestrator(adversarial_agent=FailingAdversarialAgent())
    report = orchestrator.execute(
        RunInput(source=SourceKind.FIXTURE, fixture_id="clean-retry-implementation")
    )

    assert_valid_report(report)
    # Upstream agent failure degrades READY_FOR_HUMAN_REVIEW to INCONCLUSIVE
    assert report.verdict == Verdict.INCONCLUSIVE
    adv_runs = [a for a in report.agent_runs if a.agent_name == "adversarial_reviewer"]
    assert len(adv_runs) == 1
    assert adv_runs[0].status == AgentStatus.FAILED
    assert any("Partial run" in lim for lim in report.limitations)


def test_cli_demo_writes_consistent_markdown_and_json(tmp_path: Path) -> None:
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "report.md"

    exit_code = cli_main(
        [
            "demo",
            "--fixture",
            "retry-limit-bug",
            "--mode",
            "deterministic",
            "--output-json",
            str(json_out),
            "--output-md",
            str(md_out),
        ]
    )
    assert exit_code == 0
    assert json_out.is_file()
    assert md_out.is_file()

    parsed = VerificationReport.model_validate(
        json.loads(json_out.read_text(encoding="utf-8"))
    )
    assert_valid_report(parsed)
    md_text = md_out.read_text(encoding="utf-8")

    assert parsed.run_id in md_text
    assert parsed.verdict.value in md_text
    for req in parsed.requirements:
        assert req.requirement_id in md_text
    for ev in parsed.evidence:
        assert ev.evidence_id in md_text


def test_repeated_offline_runs_are_structurally_deterministic() -> None:
    orchestrator = PatchProofOrchestrator(config=PatchProofConfig())
    r1 = orchestrator.execute(RunInput(source=SourceKind.FIXTURE, fixture_id="retry-limit-bug"))
    r2 = orchestrator.execute(RunInput(source=SourceKind.FIXTURE, fixture_id="retry-limit-bug"))

    assert r1.run_id == r2.run_id
    assert r1.source.snapshot_hash == r2.source.snapshot_hash
    assert r1.verdict == r2.verdict
    assert [r.model_dump() for r in r1.requirements] == [
        r.model_dump() for r in r2.requirements
    ]
    assert [f.model_dump() for f in r1.findings] == [f.model_dump() for f in r2.findings]


def test_missing_acceptance_criteria_yields_inferred_ambiguous_and_inconclusive(
    tmp_path: Path,
) -> None:
    fix_dir = tmp_path / "vague-issue"
    fix_dir.mkdir(parents=True)
    (fix_dir / "src").mkdir()
    (fix_dir / "src" / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
    (fix_dir / "diff.patch").write_text(
        "--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,2 @@\n+def run():\n+    return True\n",
        encoding="utf-8",
    )
    manifest = {
        "repository": "synthetic/vague-issue",
        "synthetic": True,
        "issue_title": "Make retry logic better and clean up appropriately",
        "issue_body": "Please make it work well as needed.",
        "diff_file": "diff.patch",
        "source_files": ["src/app.py"],
        "test_files": [],
    }
    (fix_dir / "fixture.json").write_text(json.dumps(manifest), encoding="utf-8")

    orchestrator = PatchProofOrchestrator(config=PatchProofConfig(fixtures_dir=tmp_path))
    report = orchestrator.execute(RunInput(source=SourceKind.FIXTURE, fixture_id="vague-issue"))

    assert_valid_report(report)
    assert report.verdict == Verdict.INCONCLUSIVE
    assert len(report.requirements) == 1
    assert report.requirements[0].origin.value == "inferred"
    assert report.requirements[0].status == RequirementStatus.AMBIGUOUS
    assert len(report.open_questions) >= 1


def test_langgraph_workflow_nodes_and_observable_order() -> None:
    orchestrator = PatchProofOrchestrator()
    ledger = EvidenceLedger()
    compiled_graph = orchestrator.build_graph(ledger)

    graph_def = compiled_graph.get_graph()
    node_names = set(graph_def.nodes.keys())
    for expected_node in GRAPH_NODE_ORDER:
        assert expected_node in node_names

    final_state = compiled_graph.invoke(
        {"run_input": RunInput(source=SourceKind.FIXTURE, fixture_id="retry-limit-bug")}
    )
    assert final_state["workflow_status"] == "COMPLETED"
    report = final_state["report"]
    assert_valid_report(report)

    event_types = [ev.event_type for ev in report.events]
    assert event_types[0] == "run_created"
    assert event_types[1] == "input_validated"
    assert event_types[2] == "source_fetch_completed"
    assert event_types[-1] == "report_validation_passed"


def test_provider_backed_orchestration_with_fake_provider_and_retry_fallback() -> None:
    call_counter = 0

    def flaky_intent_response(ctx: dict[str, object]) -> dict[str, object]:
        nonlocal call_counter
        call_counter += 1
        if call_counter == 1:
            # First attempt returns malformed payload -> triggers bounded retry
            return {"malformed": "schema"}
        return {
            "agent_name": "intent_analyst",
            "schema_version": "1.0",
            "status": "SUCCEEDED",
            "summary": "Provider extracted 1 requirement after retry",
            "evidence_ids": ["E-001"],
            "warnings": [],
            "duration_ms": 2,
            "requirements": [
                {
                    "requirement_id": "R-001",
                    "text": "Must retry transient failures at most max_retries times",
                    "origin": "explicit",
                    "status": "UNVERIFIED",
                    "evidence_ids": ["E-001"],
                    "notes": [],
                    "code_locations": [],
                    "test_ids": [],
                }
            ],
            "ambiguity_questions": [],
        }

    fake_provider = DeterministicFakeLLMProvider(
        responses={
            "intent_analyst": flaky_intent_response,
            # Other roles are omitted from fake_provider so they test deterministic fallback
        }
    )
    config = PatchProofConfig(max_model_calls=10, max_retries_per_agent=1)
    orchestrator = PatchProofOrchestrator(config=config, provider=fake_provider)
    report = orchestrator.execute(
        RunInput(
            source=SourceKind.FIXTURE,
            fixture_id="retry-limit-bug",
            model_mode="provider",  # type: ignore[arg-type]
        )
    )

    assert_valid_report(report)
    assert call_counter == 2
    assert report.verdict == Verdict.CHANGES_REQUESTED
    assert len(report.requirements) == 1
    assert report.requirements[0].requirement_id == "R-001"
    # Roles without fake responses fell back deterministically with a recorded warning
    change_run = next(a for a in report.agent_runs if a.agent_name == "change_investigator")
    assert any("deterministic fallback" in w for w in change_run.warnings)


def test_budgeted_provider_enforces_max_model_calls() -> None:
    fake_provider = DeterministicFakeLLMProvider(responses={})
    budgeted = BudgetedLLMProvider(
        fake_provider,
        max_model_calls=2,
        max_retries_per_agent=2,
    )
    try:
        budgeted.generate_structured(
            role="intent_analyst",
            system_prompt="test",
            untrusted_context={},
            response_schema=Requirement,
        )
    except ProviderBudgetExceededError:
        pass
    assert budgeted.call_count == 2
    assert budgeted.retry_count == 1


def test_fastapi_web_ui_and_api_contract() -> None:
    from patchproof.api.app import create_app

    app = create_app()
    routes = {getattr(r, "path", ""): getattr(r, "endpoint", None) for r in app.routes}
    assert "/" in routes
    assert "/api/v1/health" in routes
    assert "/api/v1/runs" in routes
    assert "/api/v1/runs/{run_id}" in routes
    assert "/api/v1/runs/{run_id}/report.md" in routes

    health_payload = routes["/api/v1/health"]()
    assert health_payload["status"] == "ok"

    ui_resp = routes["/"]()
    assert ui_resp.status_code == 200
    assert "Multi-Agent LangGraph Verification Architecture" in bytes(ui_resp.body).decode(
        "utf-8"
    )

    run_payload = routes["/api/v1/runs"](
        {
            "source": "fixture",
            "fixture_id": "retry-limit-bug",
            "execution_mode": "static_only",
            "model_mode": "deterministic",
        }
    )
    run_id = run_payload["run_id"]
    assert run_payload["verdict"] == "CHANGES_REQUESTED"

    fetched = routes["/api/v1/runs/{run_id}"](run_id=run_id)
    assert fetched["run_id"] == run_id

    md_resp = routes["/api/v1/runs/{run_id}/report.md"](run_id=run_id)
    assert "# PatchProof Verification Report" in bytes(md_resp.body).decode("utf-8")




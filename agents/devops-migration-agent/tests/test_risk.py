"""Unit tests for deterministic risk assessor."""

from models.github_workflow import GitHubWorkflow, WorkflowJob, WorkflowStep
from models.migration_report import (
    ActionMappingResult,
    ActionMappingStatus,
    TerraformAnalysisResult,
)
from models.risk_model import RiskLevel
from tools.risk_assessor import assess_migration_risk


def test_low_risk_workflow():
    wf = GitHubWorkflow(
        name="Simple CI",
        jobs={
            "test": WorkflowJob(
                id="test",
                steps=[WorkflowStep(uses="actions/checkout@v4")],
            )
        },
    )
    mapping = [
        ActionMappingResult(
            action_name="actions/checkout",
            status=ActionMappingStatus.DIRECT,
            ado_task="checkout",
        )
    ]
    risk = assess_migration_risk(wf, mapping)
    assert risk.overall_score < 25
    assert risk.overall_level == RiskLevel.LOW
    assert len(risk.blockers) == 0


def test_critical_risk_on_unsupported_action():
    wf = GitHubWorkflow(name="Blocked CI")
    mapping = [
        ActionMappingResult(
            action_name="github/codeql-action",
            status=ActionMappingStatus.UNSUPPORTED,
            warnings=["Unsupported"],
        )
    ]
    risk = assess_migration_risk(wf, mapping)
    assert risk.overall_level == RiskLevel.CRITICAL
    assert len(risk.blockers) == 1
    assert any("Unsupported" in b for b in risk.blockers)


def test_hardcoded_secret_detection_triggers_blocker():
    wf = GitHubWorkflow(name="Leaked Secret")
    mapping = []
    raw = "env:\n  TOKEN: ghp_123456789012345678901234567890123456"
    risk = assess_migration_risk(wf, mapping, raw_content=raw)

    assert risk.overall_level == RiskLevel.CRITICAL
    assert any("Hardcoded" in b for b in risk.blockers)


def test_terraform_missing_backend_adds_risk():
    wf = GitHubWorkflow(name="TF CI")
    mapping = []
    tf_res = TerraformAnalysisResult(
        has_terraform=True,
        file_count=2,
        backend_type=None,
        service_connections_needed=["AzureRM"],
    )
    risk = assess_migration_risk(wf, mapping, tf_result=tf_res)
    assert any("Terraform Missing Remote Backend" in i.title for i in risk.items)

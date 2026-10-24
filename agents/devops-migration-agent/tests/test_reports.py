"""Unit tests for report generation and JSON schema compliance."""

import json
from pathlib import Path

import jsonschema

from models.github_workflow import GitHubWorkflow, WorkflowJob, WorkflowStep
from models.migration_report import ActionMappingResult, ActionMappingStatus, ValidationResult
from models.risk_model import RiskAssessment, RiskLevel
from tools.report_generator import (
    build_migration_summary,
    write_all_reports,
)


def test_write_all_reports_generates_all_files(tmp_path):
    wf = GitHubWorkflow(
        name="Test Workflow",
        file_path="test.yml",
        jobs={"job1": WorkflowJob(id="job1", steps=[WorkflowStep(uses="actions/checkout@v4")])},
    )
    mappings = [
        ActionMappingResult(
            action_name="actions/checkout",
            status=ActionMappingStatus.DIRECT,
            ado_task="checkout",
        )
    ]
    validation = ValidationResult(is_valid=True)
    risk = RiskAssessment(overall_score=10, overall_level=RiskLevel.LOW)

    _ = write_all_reports(
        output_dir=tmp_path,
        workflow=wf,
        mappings=mappings,
        pipeline_yaml="jobs: []",
        validation=validation,
        risk=risk,
        tf_result=None,
    )

    expected_files = [
        "generated-pipeline.yml",
        "migration-report.md",
        "risk-assessment.md",
        "migration-checklist.md",
        "migration-summary.json",
        "validation-results.json",
    ]

    for fname in expected_files:
        p = tmp_path / fname
        assert p.is_file(), f"Expected deliverable missing: {fname}"
        assert p.stat().st_size > 0, f"File {fname} is empty"


def test_summary_conforms_to_json_schema(tmp_path):
    schema_path = Path(__file__).parent.parent / "schemas" / "migration-summary.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    wf = GitHubWorkflow(
        name="Schema Test",
        jobs={"build": WorkflowJob(id="build", steps=[WorkflowStep(run="echo hi")])},
    )
    risk = RiskAssessment(overall_score=20, overall_level=RiskLevel.LOW)
    summary = build_migration_summary(wf, [], risk, None)

    summary_dict = json.loads(summary.model_dump_json())
    # jsonschema validate will raise if non-conforming
    jsonschema.validate(instance=summary_dict, schema=schema)

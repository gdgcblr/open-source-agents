"""Tests for CodeGenerator."""

from pathlib import Path
from agentfeat.core.generator import CodeGenerator
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan, PlanStep


def test_code_generator_creates_diffs(tmp_path: Path):
    app_file = tmp_path / "app.py"
    app_file.write_text("def index():\n    return 'old'\n", encoding="utf-8")

    plan = FeaturePlan(
        feature_title="Sample Feature",
        summary="Test summary",
        architecture_notes="Notes",
        steps=[
            PlanStep(
                step_number=1,
                title="Update App",
                action="modify",
                target_file="app.py",
                description="Update index function",
            ),
            PlanStep(
                step_number=2,
                title="Add Test",
                action="create",
                target_file="tests/test_app.py",
                description="Write unit test",
            ),
        ],
        new_dependencies=[],
        test_strategy="Run pytest",
        risk_assessment="None",
    )

    summary = CodebaseSummary(
        root_path=str(tmp_path),
        total_files=1,
        languages=["Python"],
    )

    client = GeminiClient(offline=True)
    generator = CodeGenerator(target_dir=tmp_path, client=client)

    changes = generator.generate_changes("Update index", plan, summary)

    assert len(changes) == 2
    assert changes[0].file_path == "app.py"
    assert changes[0].diff is not None
    assert changes[1].file_path == "tests/test_app.py"
    assert changes[1].action == "create"

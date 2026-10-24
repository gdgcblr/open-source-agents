"""Tests for FeaturePlanner."""

from agentfeat.core.planner import FeaturePlanner
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan


def test_feature_planner_offline_mode():
    client = GeminiClient(offline=True)
    planner = FeaturePlanner(client=client)

    summary = CodebaseSummary(
        root_path="/tmp/project",
        total_files=5,
        languages=["Python"],
        frameworks=["FastAPI"],
        manifest_files=["requirements.txt"],
        file_tree="project/\n└── app.py",
    )

    plan = planner.create_plan("Add Google OAuth login", summary)

    assert isinstance(plan, FeaturePlan)
    assert plan.feature_title is not None
    assert len(plan.steps) > 0
    assert any(s.action == "create" or s.action == "modify" for s in plan.steps)

"""Unit tests for Google ADK Agent integration and tool declarations."""

from pathlib import Path

from agent import (
    create_adk_agent,
    tool_assess_risk,
    tool_map_actions,
    tool_parse_github_workflow,
    tool_validate_terraform,
)
from config import get_config


def test_tool_parse_github_workflow():
    sample_wf = Path(__file__).parent.parent / "samples" / "github-action-example.yml"
    res = tool_parse_github_workflow(str(sample_wf))
    assert res["name"] == "CI/CD Production Build and Deploy"
    assert res["total_jobs"] == 2
    assert "REGISTRY_PASSWORD" in res["detected_secrets"]


def test_tool_map_actions():
    sample_wf = Path(__file__).parent.parent / "samples" / "github-action-example.yml"
    res = tool_map_actions(str(sample_wf))
    assert isinstance(res, list)
    assert len(res) > 0
    action_names = [a["action_name"] for a in res]
    assert "actions/checkout" in action_names
    assert "actions/setup-python" in action_names
    assert "docker/build-push-action" in action_names


def test_tool_validate_terraform():
    sample_tf = Path(__file__).parent.parent / "samples" / "terraform-example"
    res = tool_validate_terraform(str(sample_tf))
    assert res["has_terraform"] is True
    assert "azurerm" in res["providers"]


def test_tool_assess_risk():
    sample_wf = Path(__file__).parent.parent / "samples" / "github-action-example.yml"
    sample_tf = Path(__file__).parent.parent / "samples" / "terraform-example"
    res = tool_assess_risk(str(sample_wf), str(sample_tf))
    assert "score" in res
    assert "level" in res
    assert res["score"] > 0


def test_create_adk_agent():
    cfg = get_config(model_name="gemini-2.5-flash")
    agent = create_adk_agent(cfg)
    assert agent is not None
    assert agent.name == "devops_migration_agent"
    assert agent.model == "gemini-2.5-flash"
    assert len(agent.tools) == 4

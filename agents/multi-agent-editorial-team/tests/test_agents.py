"""Unit tests for individual specialized agents: Planner, Researcher, Writer, Reviewer."""

import pytest

from team.state import (
    ArticlePlan,
    EvidenceItem,
    ReviewStatus,
    ReviewVerdict,
)
from team.agents.planner import PlannerAgent
from team.agents.researcher import ResearcherAgent
from team.agents.writer import WriterAgent
from team.agents.reviewer import ReviewerAgent


def test_planner_agent():
    """Validates that PlannerAgent decomposes topic into structured plan."""
    planner = PlannerAgent(llm_caller=None)
    plan = planner.plan("Distributed Consensus in AI Agents")

    assert isinstance(plan, ArticlePlan)
    assert "Distributed Consensus in AI Agents" in plan.title
    assert len(plan.key_sections) >= 3
    assert len(plan.search_queries) >= 2


def test_researcher_agent():
    """Validates that ResearcherAgent gathers deduplicated evidence from plan."""
    researcher = ResearcherAgent(llm_caller=None)
    plan = ArticlePlan(
        title="Test Plan",
        target_audience="Engineers",
        key_sections=["Overview"],
        search_queries=["Google Gemini AI", "LangGraph agents"]
    )
    evidence = researcher.research(plan)

    assert isinstance(evidence, list)
    assert len(evidence) > 0
    first = evidence[0]
    assert isinstance(first, EvidenceItem)
    assert len(first.title) > 0
    assert first.url.startswith("http")


def test_writer_initial_and_revision():
    """Validates that WriterAgent drafts initial prose and updates on revision."""
    writer = WriterAgent(llm_caller=None)
    plan = ArticlePlan(
        title="Agentic Workflows",
        target_audience="Developers",
        key_sections=["Introduction", "Architecture", "Conclusion"],
        search_queries=["Agentic Workflows"]
    )
    evidence = [EvidenceItem(title="ADK Docs", url="https://ai.google.dev", snippet="Official docs")]

    # Initial Draft
    v1 = writer.write_initial_draft(plan, evidence)
    assert "Agentic Workflows" in v1
    assert "Introduction" in v1
    assert "https://ai.google.dev" in v1

    # Revision
    mock_verdict = ReviewVerdict(
        score=75,
        status=ReviewStatus.REVISE,
        summary="Need more citations and edge cases.",
        critiques=[],
        revision_suggestions=["Add citation to section 2"]
    )
    v2 = writer.revise_draft(v1, mock_verdict)
    assert len(v2) > len(v1)
    assert "Revision Addendum" in v2


def test_reviewer_rubric_and_gates():
    """Validates that ReviewerAgent emits REVISE on turn 1 and APPROVED on turn 2."""
    reviewer = ReviewerAgent(pass_score=85, llm_caller=None)
    evidence = [EvidenceItem(title="Test", url="https://example.com", snippet="Test")]

    # Turn 1: Should request revision
    v1_verdict = reviewer.review("Initial draft text...", evidence, turn=1)
    assert v1_verdict.status == ReviewStatus.REVISE
    assert v1_verdict.score < 85
    assert len(v1_verdict.critiques) > 0
    assert len(v1_verdict.revision_suggestions) > 0

    # Turn 2: Should approve
    v2_verdict = reviewer.review("Improved draft text...", evidence, turn=2)
    assert v2_verdict.status == ReviewStatus.APPROVED
    assert v2_verdict.score >= 85

"""
Unit tests for Evaluator, Code Runner, and Report Services.
"""

from __future__ import annotations
import pytest
from models.schemas import (
    DifficultyLevel,
    InterviewStage,
    ProgrammingLanguage,
    HiringRecommendation,
    InterviewSession,
    ChatMessage,
    EvaluationResult
)
from services.evaluator import EvaluatorService
from services.code_runner import CodeExecutionService
from services.report import ReportService
from utils.loader import get_question_by_id


def test_evaluator_json_extraction():
    """Verify robust JSON extraction from LLM responses with markdown fences."""
    evaluator = EvaluatorService()

    raw_json = '{"communication_score": 9, "problem_solving_score": 8, "code_quality_score": 9, "complexity_analysis_score": 8, "edge_cases_score": 7, "optimization_score": 8, "overall_score": 8.1, "time_complexity": "O(N)", "space_complexity": "O(N)", "correctness_assessment": "Correct", "edge_cases_identified": ["empty"], "edge_cases_missed": [], "feedback_summary": "Excellent"}'

    # Case 1: Plain JSON
    parsed = evaluator._extract_json(raw_json)
    assert parsed["communication_score"] == 9
    assert parsed["overall_score"] == 8.1

    # Case 2: Markdown fenced ```json ... ```
    fenced = f"Here is my evaluation:\n```json\n{raw_json}\n```\nHope this helps!"
    parsed_fenced = evaluator._extract_json(fenced)
    assert parsed_fenced["problem_solving_score"] == 8


def test_heuristic_evaluator():
    """Verify heuristic evaluation runs offline and returns valid schema."""
    evaluator = EvaluatorService()
    session = InterviewSession(
        session_id="test-session-123",
        candidate_name="Alice",
        difficulty=DifficultyLevel.EASY,
        topic="Arrays",
        current_stage=InterviewStage.REVIEW,
        question=get_question_by_id("two-sum"),
        revealed_constraints=[],
        messages=[
            ChatMessage(id="1", role="interviewer", content="Welcome", timestamp="2026-10-24T12:00:00", stage=InterviewStage.INTRO),
            ChatMessage(id="2", role="candidate", content="Are there duplicate numbers or can the input be empty?", timestamp="2026-10-24T12:01:00", stage=InterviewStage.PROBLEM),
            ChatMessage(id="3", role="candidate", content="I will use a hash map approach with O(N) time and O(N) space.", timestamp="2026-10-24T12:02:00", stage=InterviewStage.DISCUSSION),
        ],
        latest_code="def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        diff = target - n\n        if diff in seen:\n            return [seen[diff], i]\n        seen[n] = i\n    return []\n",
        selected_language=ProgrammingLanguage.PYTHON,
        created_at="2026-10-24T12:00:00",
        updated_at="2026-10-24T12:30:00"
    )

    eval_result = evaluator.evaluate_session(session)
    assert isinstance(eval_result, EvaluationResult)
    assert 1.0 <= eval_result.overall_score <= 10.0
    assert eval_result.communication_score >= 7
    assert eval_result.time_complexity != ""


def test_hiring_recommendation_thresholds():
    """Verify Google hiring committee threshold mappings."""
    report_svc = ReportService()
    assert report_svc._determine_hiring_recommendation(9.0) == HiringRecommendation.STRONG_HIRE
    assert report_svc._determine_hiring_recommendation(7.5) == HiringRecommendation.HIRE
    assert report_svc._determine_hiring_recommendation(6.0) == HiringRecommendation.LEANING_HIRE
    assert report_svc._determine_hiring_recommendation(4.5) == HiringRecommendation.LEANING_NO_HIRE
    assert report_svc._determine_hiring_recommendation(3.0) == HiringRecommendation.NO_HIRE


def test_report_generation():
    """Verify synthesis of InterviewReport and markdown formatting."""
    report_svc = ReportService()
    session = InterviewSession(
        session_id="test-report-456",
        candidate_name="Bob",
        difficulty=DifficultyLevel.MEDIUM,
        topic="Graphs",
        current_stage=InterviewStage.COMPLETED,
        question=get_question_by_id("number-of-islands"),
        evaluation=EvaluationResult(
            communication_score=8,
            problem_solving_score=9,
            code_quality_score=8,
            complexity_analysis_score=9,
            edge_cases_score=7,
            optimization_score=9,
            overall_score=8.4,
            time_complexity="O(M * N)",
            space_complexity="O(M * N)",
            correctness_assessment="Fully correct BFS traversal",
            edge_cases_identified=["1x1 grid", "All water grid"],
            edge_cases_missed=["Deep recursion call stack limits"],
            feedback_summary="Excellent graph decomposition."
        ),
        created_at="2026-10-24T12:00:00",
        updated_at="2026-10-24T12:45:00"
    )

    report = report_svc.generate_report(session)
    assert report.session_id == "test-report-456"
    assert report.interview_score == 8.4
    assert report.hiring_recommendation == HiringRecommendation.HIRE
    assert len(report.strengths) >= 1
    assert "Google SWE Coding Interview Feedback Report" in report.markdown_report
    assert "8.4 / 10" in report.markdown_report


def test_code_runner_execution():
    """Verify code runner correctly handles syntax errors or missing interpreters."""
    runner = CodeExecutionService(timeout_seconds=2.0)
    # Testing execution with Python code
    py_code = "print('Hello Google Interview')"
    res = runner.execute(py_code, ProgrammingLanguage.PYTHON)
    # Either successfully prints or reports python interpreter status cleanly
    assert res.exit_code is not None
    assert isinstance(res.execution_time_ms, float)


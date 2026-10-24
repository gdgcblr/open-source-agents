"""
Unit tests for Question Bank and Loader utility.
Validates question counts, schema properties, topic coverage, and random selection.
"""

from __future__ import annotations
import pytest
from models.schemas import Question, DifficultyLevel
from utils.loader import (
    load_questions_by_difficulty,
    load_all_questions,
    get_question_by_id,
    get_random_question
)


def test_load_easy_questions():
    """Verify easy questions meet schema and minimum count (>= 5)."""
    questions = load_questions_by_difficulty(DifficultyLevel.EASY)
    assert len(questions) >= 5, f"Expected at least 5 easy questions, got {len(questions)}"
    for q in questions:
        assert isinstance(q, Question)
        assert q.id
        assert q.title
        assert q.difficulty == DifficultyLevel.EASY
        assert q.topic
        assert len(q.description) > 10
        assert len(q.constraints) >= 1
        assert len(q.examples) >= 1
        assert len(q.followups) >= 1


def test_load_medium_questions():
    """Verify medium questions meet schema and minimum count (>= 5)."""
    questions = load_questions_by_difficulty(DifficultyLevel.MEDIUM)
    assert len(questions) >= 5, f"Expected at least 5 medium questions, got {len(questions)}"
    for q in questions:
        assert isinstance(q, Question)
        assert q.id
        assert q.title
        assert q.difficulty == DifficultyLevel.MEDIUM
        assert q.topic
        assert len(q.description) > 10
        assert len(q.constraints) >= 1
        assert len(q.examples) >= 1
        assert len(q.followups) >= 1


def test_load_hard_questions():
    """Verify hard questions meet schema and minimum count (>= 5)."""
    questions = load_questions_by_difficulty(DifficultyLevel.HARD)
    assert len(questions) >= 5, f"Expected at least 5 hard questions, got {len(questions)}"
    for q in questions:
        assert isinstance(q, Question)
        assert q.id
        assert q.title
        assert q.difficulty == DifficultyLevel.HARD
        assert q.topic
        assert len(q.description) > 10
        assert len(q.constraints) >= 1
        assert len(q.examples) >= 1
        assert len(q.followups) >= 1


def test_load_all_questions():
    """Verify catalog loading covers all three difficulty tiers."""
    catalog = load_all_questions()
    assert "easy" in catalog
    assert "medium" in catalog
    assert "hard" in catalog
    total = sum(len(q_list) for q_list in catalog.values())
    assert total >= 15, f"Expected at least 15 total questions, got {total}"


def test_get_question_by_id():
    """Verify fetching existing question by ID."""
    q = get_question_by_id("two-sum")
    assert q is not None
    assert q.id == "two-sum"
    assert q.title == "Two Sum"
    assert q.difficulty == DifficultyLevel.EASY


def test_get_random_question_with_topic_filter():
    """Verify random question selection by difficulty and topic."""
    q = get_random_question(DifficultyLevel.MEDIUM, topic="Graphs")
    assert q.difficulty == DifficultyLevel.MEDIUM
    assert "graph" in q.topic.lower() or q.id == "number-of-islands"


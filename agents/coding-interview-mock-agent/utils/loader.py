"""
Question and Prompt Loader Utility.
Provides resilient file loading, schema validation, and question selection across difficulties and topics.
"""

from __future__ import annotations
import json
import os
import random
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from models.schemas import Question, DifficultyLevel


# Base directory for the coding-interview-mock-agent project
BASE_DIR = Path(__file__).resolve().parent.parent
QUESTION_BANK_DIR = BASE_DIR / "question_bank"
PROMPTS_DIR = BASE_DIR / "prompts"


def get_question_file_path(difficulty: Union[str, DifficultyLevel]) -> Path:
    """Return the absolute path for a difficulty question file."""
    diff_val = difficulty.value if isinstance(difficulty, DifficultyLevel) else str(difficulty).lower()
    return QUESTION_BANK_DIR / f"{diff_val}.json"


def load_questions_by_difficulty(difficulty: Union[str, DifficultyLevel]) -> List[Question]:
    """
    Load and parse all questions for a specific difficulty level.
    Returns validated Question Pydantic instances.
    """
    file_path = get_question_file_path(difficulty)
    if not file_path.exists():
        raise FileNotFoundError(f"Question file not found at: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of questions in {file_path}, got {type(data)}")

    questions: List[Question] = []
    for item in data:
        try:
            questions.append(Question(**item))
        except Exception as e:
            # Continue loading other valid questions while logging validation issues
            print(f"[Warning] Failed to validate question {item.get('id', 'unknown')}: {e}")
    return questions


def load_all_questions() -> Dict[str, List[Question]]:
    """Load all questions categorized by difficulty level."""
    result: Dict[str, List[Question]] = {}
    for diff in [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]:
        try:
            result[diff.value] = load_questions_by_difficulty(diff)
        except Exception as e:
            result[diff.value] = []
            print(f"[Warning] Could not load {diff.value} questions: {e}")
    return result


def get_question_by_id(question_id: str) -> Optional[Question]:
    """Retrieve a specific question by unique ID across all difficulties."""
    for diff in [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]:
        questions = load_questions_by_difficulty(diff)
        for q in questions:
            if q.id == question_id:
                return q
    return None


def get_random_question(
    difficulty: Union[str, DifficultyLevel] = DifficultyLevel.MEDIUM,
    topic: Optional[str] = None
) -> Question:
    """
    Select a random question matching the specified difficulty and optional topic.
    If no topic match is found, falls back to any question in that difficulty.
    """
    questions = load_questions_by_difficulty(difficulty)
    if not questions:
        raise ValueError(f"No questions available for difficulty '{difficulty}'")

    if topic:
        topic_lower = topic.strip().lower()
        matched = [q for q in questions if topic_lower in q.topic.lower()]
        if matched:
            return random.choice(matched)

    return random.choice(questions)


def load_prompt(prompt_name: str) -> str:
    """
    Load raw prompt text from the prompts directory.
    prompt_name can be with or without '.txt' extension.
    """
    if not prompt_name.endswith(".txt"):
        prompt_name = f"{prompt_name}.txt"

    prompt_path = PROMPTS_DIR / prompt_name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


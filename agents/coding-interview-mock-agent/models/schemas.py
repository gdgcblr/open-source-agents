"""
Pydantic Models and Schemas for Coding Interview Mock Agent.
Defines data structures for questions, sessions, messages, evaluations, and reports.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class InterviewStage(str, Enum):
    INTRO = "intro"
    PROBLEM = "problem"
    DISCUSSION = "discussion"
    CODING = "coding"
    REVIEW = "review"
    FOLLOWUP = "followup"
    FEEDBACK = "feedback"
    COMPLETED = "completed"


class ProgrammingLanguage(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    CPP = "cpp"
    JAVA = "java"


class HiringRecommendation(str, Enum):
    STRONG_HIRE = "Strong Hire"
    HIRE = "Hire"
    LEANING_HIRE = "Leaning Hire"
    LEANING_NO_HIRE = "Leaning No Hire"
    NO_HIRE = "No Hire"


class ExampleCase(BaseModel):
    input: str
    output: str
    explanation: Optional[str] = None


class TestCase(BaseModel):
    input: str
    expected_output: str
    is_hidden: bool = False


class Question(BaseModel):
    id: str
    title: str
    difficulty: DifficultyLevel
    topic: str
    description: str
    constraints: List[str] = Field(default_factory=list)
    examples: List[ExampleCase] = Field(default_factory=list)
    followups: List[str] = Field(default_factory=list)
    starter_code: Dict[str, str] = Field(default_factory=dict)
    test_cases: Optional[List[TestCase]] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: str
    role: str = Field(description="Role: 'interviewer', 'candidate', or 'system'")
    content: str
    timestamp: str
    stage: InterviewStage


class CodeSubmission(BaseModel):
    language: ProgrammingLanguage
    code: str
    submitted_at: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    execution_time_ms: Optional[float] = None
    passed: Optional[bool] = None


class EvaluationResult(BaseModel):
    communication_score: int = Field(ge=1, le=10, description="Clarity, thinking aloud, asking questions")
    problem_solving_score: int = Field(ge=1, le=10, description="Decomposition, approach validity, optimality")
    code_quality_score: int = Field(ge=1, le=10, description="Cleanliness, idiomatic style, modularity")
    complexity_analysis_score: int = Field(ge=1, le=10, description="Accurate Time & Space Big-O analysis")
    edge_cases_score: int = Field(ge=1, le=10, description="Coverage of edge cases and boundary conditions")
    optimization_score: int = Field(ge=1, le=10, description="Ability to optimize from brute force")
    overall_score: float = Field(ge=1.0, le=10.0, description="Weighted composite score out of 10")
    time_complexity: str = Field(default="Not specified")
    space_complexity: str = Field(default="Not specified")
    correctness_assessment: str = Field(default="")
    edge_cases_identified: List[str] = Field(default_factory=list)
    edge_cases_missed: List[str] = Field(default_factory=list)
    feedback_summary: str = Field(default="")


class InterviewReport(BaseModel):
    session_id: str
    candidate_name: str
    difficulty: DifficultyLevel
    question_title: str
    question_topic: str
    duration_seconds: int = 0
    interview_score: float = Field(ge=0.0, le=10.0)
    hiring_recommendation: HiringRecommendation
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommended_topics: List[str] = Field(default_factory=list)
    rubric_breakdown: Dict[str, int] = Field(default_factory=dict)
    detailed_feedback: str = ""
    code_review_notes: str = ""
    markdown_report: str = ""


class InterviewSession(BaseModel):
    session_id: str
    candidate_name: str = "Candidate"
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    topic: Optional[str] = None
    current_stage: InterviewStage = InterviewStage.INTRO
    question: Optional[Question] = None
    revealed_constraints: List[str] = Field(default_factory=list)
    messages: List[ChatMessage] = Field(default_factory=list)
    code_submissions: List[CodeSubmission] = Field(default_factory=list)
    latest_code: Optional[str] = None
    selected_language: ProgrammingLanguage = ProgrammingLanguage.PYTHON
    evaluation: Optional[EvaluationResult] = None
    report: Optional[InterviewReport] = None
    created_at: str
    updated_at: str


# =====================================================================
# API Request / Response Schemas
# =====================================================================

class StartInterviewRequest(BaseModel):
    candidate_name: Optional[str] = "Candidate"
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    topic: Optional[str] = None
    language: Optional[ProgrammingLanguage] = ProgrammingLanguage.PYTHON


class StartInterviewResponse(BaseModel):
    session_id: str
    stage: InterviewStage
    message: str
    question_title: str
    question_topic: str
    starter_code: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    response: str
    stage: InterviewStage
    stage_changed: bool = False
    revealed_constraints: List[str] = Field(default_factory=list)


class RunCodeRequest(BaseModel):
    code: str
    language: ProgrammingLanguage = ProgrammingLanguage.PYTHON
    stdin: Optional[str] = ""


class RunCodeResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    success: bool
    details: Optional[str] = None


class SubmitCodeRequest(BaseModel):
    code: str
    language: ProgrammingLanguage = ProgrammingLanguage.PYTHON


class AdvanceStageRequest(BaseModel):
    next_stage: Optional[InterviewStage] = None


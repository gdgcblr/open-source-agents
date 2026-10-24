"""Domain entities. Pure data: no I/O, no framework imports."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    FLAKY = "FLAKY"
    INFRA = "INFRA"
    REGRESSION = "REGRESSION"
    UNKNOWN = "UNKNOWN"


class TestFailure(BaseModel):
    __test__ = False  # keep pytest from collecting this class

    name: str
    classname: str = ""
    message: str = ""
    details: str = ""
    rerun_recorded: bool = False  # the JUnit file records a retry for this test
    rerun_passed: bool = False


class Verdict(BaseModel):
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    suggested_action: str = ""
    source: str = "rules"  # "rules" | "llm" | "mock" | "guardrail"


class RunInput(BaseModel):
    """Everything the triage use-case needs, already loaded and parsed."""

    failures: list[TestFailure]
    total_tests: int
    log_lines: list[str] = Field(default_factory=list)
    history: Optional[dict[str, list[str]]] = None


class TriagedFailure(BaseModel):
    failure: TestFailure
    verdict: Verdict
    note: Optional[str] = None


class TriageResult(BaseModel):
    results: list[TriagedFailure]
    total_tests: int
    pii_counts: dict[str, int] = Field(default_factory=dict)  # counts only, never values

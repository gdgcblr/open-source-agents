"""Structured RCA report produced by the Scribe agent."""

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["code", "config", "infrastructure", "dependencies", "data", "traffic"]
CATEGORIES: tuple[str, ...] = Category.__args__  # type: ignore[attr-defined]

Verdict = Literal["root_cause", "contributing", "refuted", "inconclusive"]


class Cause(BaseModel):
    category: Category
    description: str = Field(description="One-line hypothesis, e.g. 'N+1 query added in a1f3c9e'")
    evidence: list[str] = Field(description="Concrete facts (log lines, metric deltas, diff lines) that support or refute it")
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)


class RCAReport(BaseModel):
    incident_title: str
    effect: str = Field(description="The observed problem: the head of the fishbone")
    root_cause: str = Field(description="One or two sentences naming the single root cause and its mechanism")
    culprit: str = Field(description="Commit sha, config key or package that introduced the root cause")
    causes: list[Cause] = Field(description="Every hypothesis examined, including refuted red herrings")
    five_whys: list[str] = Field(description="Chain of 5 whys from symptom down to process gap")
    immediate_fix: str = Field(description="Exact containment step, e.g. a git revert or gcloud command")
    corrective_actions: list[str]
    preventive_actions: list[str] = Field(description="Process/test changes so this class of failure cannot recur")

"""Data models and schemas for Prompt Context Linter and Formatter."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LintSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LintIssue(BaseModel):
    """Represents a single prompt template linting issue or smell."""
    rule_id: str
    message: str
    line_number: Optional[int] = None
    severity: LintSeverity = LintSeverity.WARNING
    suggestion: str = ""


class LintReport(BaseModel):
    """Comprehensive analysis report produced by the prompt linter."""
    is_valid: bool
    template_name: str = "prompt_template"
    total_issues: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    issues: List[LintIssue] = Field(default_factory=list)
    variables_found: List[str] = Field(default_factory=list)
    variables_missing: List[str] = Field(default_factory=list)
    variables_unused: List[str] = Field(default_factory=list)
    raw_character_count: int = 0
    estimated_token_count: int = 0
    interpolated_preview: str = ""


class TruncationPolicy(str, Enum):
    HEAD = "head"
    TAIL = "tail"
    SANDWICH = "sandwich"


class TruncationResult(BaseModel):
    """Output metadata from context budget truncation."""
    original_characters: int
    final_characters: int
    original_estimated_tokens: int
    final_estimated_tokens: int
    truncated: bool
    policy_used: TruncationPolicy
    characters_removed: int
    content: str

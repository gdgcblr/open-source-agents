"""Prompts package for DevOps Migration Agent."""

from prompts.migration_prompt import (
    MIGRATION_ANALYSIS_PROMPT,
    MIGRATION_SYSTEM_INSTRUCTION,
)
from prompts.review_prompt import (
    REVIEW_PIPELINE_PROMPT,
    REVIEW_SYSTEM_INSTRUCTION,
)
from prompts.terraform_prompt import (
    TERRAFORM_ANALYSIS_PROMPT,
    TERRAFORM_SYSTEM_INSTRUCTION,
)

__all__ = [
    "MIGRATION_ANALYSIS_PROMPT",
    "MIGRATION_SYSTEM_INSTRUCTION",
    "REVIEW_PIPELINE_PROMPT",
    "REVIEW_SYSTEM_INSTRUCTION",
    "TERRAFORM_ANALYSIS_PROMPT",
    "TERRAFORM_SYSTEM_INSTRUCTION",
]

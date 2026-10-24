"""Pydantic schemas representing AgentFeat internal states and LLM outputs."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class FileContext(BaseModel):
    """Context representation of an inspected file."""

    path: str = Field(description="Relative path of the file from project root")
    size_bytes: int = Field(default=0, description="Size of the file in bytes")
    language: str = Field(default="unknown", description="Programming language or file type")
    content: str = Field(default="", description="Content or interface snippet of the file")
    is_truncated: bool = Field(default=False, description="True if content was truncated to fit context limits")


class CodebaseSummary(BaseModel):
    """Summary of an inspected codebase."""

    root_path: str = Field(description="Absolute path of the scanned repository root")
    total_files: int = Field(default=0, description="Total number of relevant files scanned")
    languages: List[str] = Field(default_factory=list, description="List of detected languages")
    frameworks: List[str] = Field(default_factory=list, description="List of detected frameworks or libraries")
    manifest_files: List[str] = Field(default_factory=list, description="Dependency and configuration manifests found")
    relevant_files: List[FileContext] = Field(default_factory=list, description="Detailed context for key files")
    file_tree: str = Field(default="", description="Hierarchical tree view of the codebase")


class PlanStep(BaseModel):
    """A discrete implementation step within a feature plan."""

    step_number: int = Field(description="Sequential order of the step")
    title: str = Field(description="Short human-readable title of the step")
    action: Literal["create", "modify", "delete", "test"] = Field(description="Primary action type")
    target_file: str = Field(description="Target file path relative to repo root")
    description: str = Field(description="Detailed rationale and technical requirements for this step")


class FeaturePlan(BaseModel):
    """The structured blueprint generated for a feature request."""

    feature_title: str = Field(description="Standardized name of the feature")
    summary: str = Field(description="High-level description of what the feature achieves")
    architecture_notes: str = Field(description="Architectural design choices and conventions followed")
    steps: List[PlanStep] = Field(default_factory=list, description="Ordered implementation steps")
    new_dependencies: List[str] = Field(default_factory=list, description="Any new packages/libraries required")
    test_strategy: str = Field(description="How the generated code will be tested and verified")
    risk_assessment: str = Field(description="Potential breaking changes, performance impact, or security considerations")


class FileChange(BaseModel):
    """A proposed change to a file."""

    file_path: str = Field(description="Relative path to the target file")
    action: Literal["create", "modify", "delete"] = Field(description="Action to perform")
    description: str = Field(description="Brief explanation of the changes made")
    original_content: Optional[str] = Field(default=None, description="Existing content before change, if any")
    new_content: str = Field(default="", description="Full proposed new content for the file")
    diff: Optional[str] = Field(default=None, description="Unified diff formatted preview")
    is_valid: bool = Field(default=True, description="Whether the file passed syntax/sanity checks")
    validation_error: Optional[str] = Field(default=None, description="Error message if syntax validation failed")


class ExecutionResult(BaseModel):
    """Overall outcome of the AgentFeat feature development pipeline."""

    feature_request: str = Field(description="The user's original feature prompt")
    plan: FeaturePlan = Field(description="The feature implementation plan")
    changes: List[FileChange] = Field(default_factory=list, description="List of generated file changes")
    applied: bool = Field(default=False, description="Whether changes were written to disk")
    validation_passed: bool = Field(default=True, description="Whether all changed files passed validation")
    backup_dir: Optional[str] = Field(default=None, description="Path to safety backup if created")
    pr_description: str = Field(default="", description="Ready-to-use Pull Request / changelog markdown")

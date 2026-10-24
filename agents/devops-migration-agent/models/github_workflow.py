"""Pydantic data models for GitHub Actions Workflows."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """Represents a single step in a GitHub Actions job."""

    id: str | None = None
    name: str | None = None
    uses: str | None = None
    run: str | None = None
    shell: str | None = None
    with_params: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    if_condition: str | None = None
    continue_on_error: bool = False
    timeout_minutes: int | None = None

    @property
    def is_action(self) -> bool:
        """Returns True if the step invokes a reusable action via uses."""
        return bool(self.uses)

    @property
    def is_script(self) -> bool:
        """Returns True if the step executes inline shell commands."""
        return bool(self.run)

    @property
    def action_name(self) -> str | None:
        """Extracts the action identifier without version tag (e.g. actions/checkout)."""
        if not self.uses:
            return None
        return self.uses.split("@")[0].strip()

    @property
    def action_version(self) -> str | None:
        """Extracts the action version tag if present (e.g. v4)."""
        if not self.uses or "@" not in self.uses:
            return None
        return self.uses.split("@", 1)[1].strip()


class WorkflowJob(BaseModel):
    """Represents a job within a GitHub Actions workflow."""

    id: str
    name: str | None = None
    runs_on: str | list[str] = "ubuntu-latest"
    needs: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)
    strategy_matrix: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    permissions: dict[str, str] | str = Field(default_factory=dict)
    timeout_minutes: int | None = None
    if_condition: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.id


class TriggerPush(BaseModel):
    """Configuration for push triggers."""

    branches: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    paths_ignore: list[str] = Field(default_factory=list)


class TriggerPullRequest(BaseModel):
    """Configuration for pull_request triggers."""

    branches: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


class TriggerSchedule(BaseModel):
    """Configuration for cron-based schedule triggers."""

    cron: list[str] = Field(default_factory=list)


class WorkflowTriggers(BaseModel):
    """Structured representation of workflow triggers."""

    push: TriggerPush | None = None
    pull_request: TriggerPullRequest | None = None
    schedule: TriggerSchedule | None = None
    workflow_dispatch: bool = False
    custom_events: list[str] = Field(default_factory=list)


class GitHubWorkflow(BaseModel):
    """Comprehensive representation of a parsed GitHub Actions workflow."""

    name: str = "GitHub Workflow"
    file_path: str = ""
    triggers: WorkflowTriggers = Field(default_factory=WorkflowTriggers)
    env: dict[str, str] = Field(default_factory=dict)
    permissions: dict[str, str] | str = Field(default_factory=dict)
    concurrency: dict[str, Any] | str | None = None
    jobs: dict[str, WorkflowJob] = Field(default_factory=dict)
    detected_secrets: list[str] = Field(default_factory=list)
    raw_ast: dict[Any, Any] = Field(default_factory=dict)

    @property
    def total_steps(self) -> int:
        return sum(len(job.steps) for job in self.jobs.values())

    @property
    def total_jobs(self) -> int:
        return len(self.jobs)

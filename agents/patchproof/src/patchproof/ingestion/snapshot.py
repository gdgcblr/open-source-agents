"""Immutable ContextSnapshot models for PatchProof runs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from patchproof.core.models import SourceRef, utc_now_iso


class FileSnapshot(BaseModel):
    """Immutable bounded snapshot of a single source or test file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    content: str
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    truncated: bool = Field(default=False)
    original_bytes: int = Field(ge=0)
    line_count: int = Field(ge=0)


class ContextSnapshot(BaseModel):
    """Immutable context snapshot shared by all agents during a run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: SourceRef
    issue_title: str = Field(default="")
    issue_body: str = Field(default="")
    pr_title: str = Field(default="")
    pr_body: str = Field(default="")
    labels: list[str] = Field(default_factory=list)
    diff_text: str = Field(default="")
    diff_truncated: bool = Field(default=False)
    source_files: dict[str, FileSnapshot] = Field(default_factory=dict)
    test_files: dict[str, FileSnapshot] = Field(default_factory=dict)
    omitted_files_count: int = Field(default=0, ge=0)
    fetched_at: str = Field(default_factory=utc_now_iso)
    issue_evidence_id: str | None = Field(default=None)
    pr_evidence_id: str | None = Field(default=None)
    diff_evidence_id: str | None = Field(default=None)
    source_evidence_ids: dict[str, str] = Field(default_factory=dict)
    test_evidence_ids: dict[str, str] = Field(default_factory=dict)


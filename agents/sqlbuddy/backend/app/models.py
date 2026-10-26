"""Validated request and response models for the versioned API."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Dialect = Literal["postgresql", "mysql", "sqlite"]


class TableSchema(BaseModel):
    """One table definition supplied by the user."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    columns: list[str] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 128:
            raise ValueError("Table names must be non-empty and no longer than 128 characters.")
        return value

    @field_validator("columns")
    @classmethod
    def clean_columns(cls, value: list[str]) -> list[str]:
        cleaned = [column.strip() for column in value]
        if any(not column or len(column) > 128 for column in cleaned):
            raise ValueError("Column names must be non-empty and no longer than 128 characters.")
        return cleaned


class SchemaInput(BaseModel):
    """Structured optional database context; never used to connect to a DB."""

    model_config = ConfigDict(extra="forbid")
    tables: list[TableSchema] = Field(default_factory=list, max_length=100)


class QueryRequest(BaseModel):
    """Request to create a SQL suggestion."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    question: str = Field(min_length=1, max_length=4000)
    dialect: Dialect = "sqlite"
    schema_context: SchemaInput | None = Field(default=None, alias="schema")
    session_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter a question.")
        return value


class GeminiAnswer(BaseModel):
    """Response fields requested from Gemini; excludes app-owned metadata."""

    model_config = ConfigDict(extra="forbid")
    sql: str = Field(max_length=12000)
    explanation: str = Field(min_length=1, max_length=8000)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=30)


class Answer(GeminiAnswer):
    """Structured assistant response shown by the frontend."""

    unverified: Literal[True] = True


class QueryResponse(BaseModel):
    session_id: UUID
    answer: Answer
    dialect: Dialect
    created_at: datetime


class SessionSummary(BaseModel):
    id: UUID
    title: str
    dialect: Dialect
    updated_at: datetime


class MessageRecord(BaseModel):
    question: str
    answer: Answer
    dialect: Dialect
    created_at: datetime


class SessionDetail(SessionSummary):
    messages: list[MessageRecord]


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Session title cannot be blank.")
        return value

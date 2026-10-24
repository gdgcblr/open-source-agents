"""Validated source notes and untrusted model proposals."""

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Kind(str, Enum):
    SPENDING = "spending"
    LENDING = "lending"
    BORROWING = "borrowing"
    REPAYMENT_RECEIVED = "repayment_received"
    REPAYMENT_PAID = "repayment_paid"
    INCOME = "income"
    TRANSFER = "transfer"
    UNKNOWN = "unknown"


class SourceNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern="^(gmail|keep|manual|demo)$")
    source_id: str = Field(min_length=1, max_length=300)
    title: str = Field(max_length=500)
    text: str = Field(min_length=1, max_length=20000)
    source_url: str = Field(default="", max_length=500)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_date: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern="^[A-Z]{3}$")
    kind: Kind
    category: str = Field(min_length=1, max_length=60)
    counterparty: str = Field(default="", max_length=120)
    reason: str = Field(min_length=10, max_length=1000)
    evidence: str = Field(min_length=1, max_length=1500)
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transactions: list[Proposal] = Field(max_length=20)
    explanation: str = Field(min_length=1, max_length=1000)
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FinancialRecord(BaseModel):
    """Extracted evidence; a candidate until the user accepts it."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["bill", "payment", "charge", "refund"]
    provider: str = Field(min_length=1, max_length=120)
    account: str = Field(default="", pattern=r"^(\d{4})?$")
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    occurred_on: date
    due_on: date | None = None
    period: str = Field(default="", pattern=r"^(\d{4}-\d{2})?$")
    status: Literal["statement", "scheduled", "received", "credited", "failed", "reversed"]
    reference: str = Field(default="", max_length=120)
    subscription: bool = False
    evidence: str = Field(min_length=8, max_length=1200)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value):
        return value.strip().casefold()

    @model_validator(mode="after")
    def valid_bill(self):
        if self.period:
            date.fromisoformat(self.period + "-01")
        if self.kind == "bill" and (not self.account or not self.due_on or not self.period):
            raise ValueError("Bills require a card, due date, and statement month.")
        if self.kind == "bill" and (self.status != "statement" or self.due_on < self.occurred_on):
            raise ValueError("Bills require statement status and a valid due date.")
        if self.kind != "bill" and self.status == "statement":
            raise ValueError("Only bills can have statement status.")
        return self


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[FinancialRecord] = Field(default_factory=list, max_length=20)

"""Data models for Gemini Audit Agent."""
from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class SettlementStatus(str, Enum):
    confirmed = "confirmed"
    pending = "pending"
    disputed = "disputed"


class Member(BaseModel):
    id: str
    name: str
    uid: Optional[str] = None
    phone_number: Optional[str] = None
    upi_id: Optional[str] = None


class Expense(BaseModel):
    id: str = Field(default_factory=lambda: f"exp_{int(datetime.now().timestamp() * 1000)}")
    description: str
    payer_id: str
    amount: float
    shares: Dict[str, float]
    category: Optional[str] = "General"
    created_at: datetime = Field(default_factory=datetime.now)


class SettlementRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"set_{int(datetime.now().timestamp() * 1000)}")
    from_member_id: str
    from_name: str
    to_member_id: str
    to_name: str
    amount: float
    status: SettlementStatus = SettlementStatus.pending
    note: Optional[str] = None
    settled_at: datetime = Field(default_factory=datetime.now)


class SettlementTransaction(BaseModel):
    from_member_id: str
    from_name: str
    to_member_id: str
    to_name: str
    amount: float
    payee_upi_id: Optional[str] = None
    payee_phone: Optional[str] = None


class AuditAnomaly(BaseModel):
    type: str  # e.g., "ID_FRAGMENTATION", "BALANCE_DRIFT", "SPLIT_MISMATCH", "PENDING_HOLD"
    description: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    suggested_fix: str


class AuditReport(BaseModel):
    is_balanced: bool
    total_spent: float
    member_balances: Dict[str, float]
    net_zero_delta: float
    anomalies: List[AuditAnomaly]
    optimal_settlements: List[SettlementTransaction]
    pending_settlements_count: int
    generated_at: datetime = Field(default_factory=datetime.now)

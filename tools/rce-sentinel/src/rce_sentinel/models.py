"""Shared data models. LLM output is validated against `Verdict` before use."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Label = Literal["low", "medium", "high", "critical"]


class Evidence(BaseModel):
    file: str
    line: int
    quote: str = Field(max_length=400)


class Verdict(BaseModel):
    """Strict schema every judge must return."""

    verdict: Literal["vulnerable", "safe", "uncertain"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list, max_length=8)
    exploit_path: str = Field(default="", max_length=600)
    suggested_fix: str = Field(default="", max_length=800)


class Dependency(BaseModel):
    ecosystem: str
    name: str
    version: str | None
    file: str


class Advisory(BaseModel):
    id: str
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    cwes: list[str] = Field(default_factory=list)
    cvss_vector: str | None = None
    fixed_version: str | None = None
    symbols: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    @property
    def cve_ids(self) -> list[str]:
        return [a for a in [self.id, *self.aliases] if a.startswith("CVE-")]


class RiskScore(BaseModel):
    score: float
    label: Label
    factors: dict[str, float | str | bool | None] = Field(default_factory=dict)


class Finding(BaseModel):
    id: str
    layer: Literal["dependency", "rule", "taint"]
    rule_id: str
    title: str
    cwe: str
    file: str
    line: int
    snippet: str = ""
    sink: str = ""
    source: str | None = None
    taint_chain: list[str] = Field(default_factory=list)
    arg_kind: Literal["tainted", "constant", "unknown"] = "unknown"
    attacker_path: str = ""
    fix: str = ""
    context_hash: str = ""
    scope: tuple[int, int] | None = None  # enclosing function lines
    dependency: Dependency | None = None
    advisory: Advisory | None = None
    reachable: bool | None = None
    reach_evidence: list[str] = Field(default_factory=list)
    risk: RiskScore | None = None
    verdict: Verdict | None = None
    decided_by: str = "rules"
    trust: int = 0
    suppressed: bool = False
    realert: str | None = None
    internal_notes: str = ""


class IntelItem(BaseModel):
    """Normalized threat-intel metadata. Never holds exploit payloads."""

    source: str
    url: str
    title: str = Field(default="", max_length=300)
    summary: str = Field(default="", max_length=800)
    cve_ids: list[str] = Field(default_factory=list)
    packages: list[dict[str, str]] = Field(default_factory=list)
    cwes: list[str] = Field(default_factory=list)
    published: str = ""
    credibility: float = 0.5
    confirmed: bool = True
    kev: bool = False
    fixed_version: str | None = None
    content_hash: str = ""


class RunStats(BaseModel):
    llm_calls: int = 0
    cache_hits: int = 0
    units_total: int = 0
    units_skipped_prerouter: int = 0
    units_judged: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class ScanReport(BaseModel):
    run_id: str
    mode: str
    started: str
    duration_s: float
    degraded: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    blocked: bool = False
    stats: RunStats = Field(default_factory=RunStats)
    versions: dict[str, str] = Field(default_factory=dict)

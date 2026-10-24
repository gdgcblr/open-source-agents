"""The model cannot write verdicts: only check implementations can."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["passed", "failed", "not_verified", "error"]


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    source: str
    line: int
    statement: str
    data: dict[str, Any] = field(repr=False)

    @classmethod
    def create(cls, kind: str, source: str, line: int, statement: str, **data: Any) -> Claim:
        digest = hashlib.sha256(f"{kind}:{source}:{line}:{statement}".encode()).hexdigest()[:12]
        return cls(digest, kind, source, line, statement, data)

    def public(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "data"}


@dataclass(frozen=True)
class Result:
    claim_id: str
    status: Status
    observed: str
    evidence: dict[str, Any] = field(default_factory=dict)


class Ledger:
    def __init__(self, claims: list[Claim]) -> None:
        self.claims = {claim.id: claim for claim in claims}
        if len(self.claims) != len(claims):
            raise ValueError("Duplicate claim IDs")
        self.results: dict[str, Result] = {}

    def get(self, claim_id: str) -> Claim:
        if claim_id not in self.claims:
            raise ValueError(f"Unknown claim ID: {claim_id}")
        return self.claims[claim_id]

    def record(self, result: Result) -> Result:
        self.get(result.claim_id)
        self.results[result.claim_id] = result
        return result

    def complete(self) -> list[Result]:
        return [
            self.results.get(
                claim.id,
                Result(claim.id, "not_verified", "No check executed; no evidence collected."),
            )
            for claim in self.claims.values()
        ]

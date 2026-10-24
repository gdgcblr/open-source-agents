"""Data model for static-analysis findings."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
    rule_id: str
    message: str
    severity: str
    path: str
    line: int
    column: int = 1
    reference: str = ""

    @classmethod
    def from_semgrep(cls, item: dict) -> "Finding":
        extra = item.get("extra") or {}
        start = item.get("start") or {}
        metadata = extra.get("metadata") or {}
        return cls(
            rule_id=str(item.get("check_id") or "unknown"),
            message=str(extra.get("message") or "No message provided"),
            severity=str(extra.get("severity") or "INFO").upper(),
            path=str(item.get("path") or "<unknown>").replace("\\", "/"),
            line=int(start.get("line") or 1),
            column=int(start.get("col") or 1),
            reference=str(metadata.get("source") or metadata.get("shortlink") or ""),
        )

"""Evidence collection, validation, indexing, and redaction for AgentRelay."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from agentrelay.schemas import EvidenceRecord, ValidationError

# Regex patterns for detecting and redacting common secrets
SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"sk-proj-[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "[REDACTED_PROJECT_KEY]"),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"gh[pousr]-[A-Za-z0-9_]{36,255}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"(password|passwd|secret|api_key|apikey|bearer)\s*[:=]\s*['\"]([^'\"]{4,})['\"]", re.IGNORECASE), r"\1='[REDACTED_SECRET]'"),
]

# Patterns for detecting prompt injection / suspicious instructions in untrusted evidence
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?(system\s+prompt|secrets|api\s*keys)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(an?\s+)?(admin|system|root)", re.IGNORECASE),
    re.compile(r"disregard\s+above", re.IGNORECASE),
    re.compile(r"output\s+only\s+['\"]?CONFIRMED['\"]?", re.IGNORECASE),
    re.compile(r"<script>.*?</script>", re.IGNORECASE | re.DOTALL),
]


def redact_secrets(text: str) -> str:
    """Redact known secret patterns from string content."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def inspect_for_prompt_injection(text: str) -> List[str]:
    """Inspect untrusted evidence for adversarial instructions.

    Returns a list of warning descriptions. Note that regex detection is heuristic
    and not guaranteed to detect all novel injections. Untrusted evidence must never
    be executed as code or unconstrained system prompts.
    """
    if not isinstance(text, str):
        return []
    warnings: List[str] = []
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            warnings.append(f"Suspicious instruction pattern detected: '{pattern.pattern}'")
    return warnings


class EvidenceStore:
    """In-memory indexed store for evidence records."""

    def __init__(self, records: Optional[Iterable[EvidenceRecord]] = None) -> None:
        self._records: Dict[str, EvidenceRecord] = {}
        self._service_index: Dict[str, Set[str]] = {}
        self._commit_index: Dict[str, Set[str]] = {}
        self._deployment_index: Dict[str, Set[str]] = {}
        self._warnings: List[str] = []

        if records:
            for record in records:
                self.add(record)

    def add(self, record: EvidenceRecord) -> None:
        """Add an evidence record after validation and redaction."""
        if not isinstance(record, EvidenceRecord):
            raise ValidationError("Item must be an EvidenceRecord instance.")

        # Sanitize content
        sanitized_content = redact_secrets(record.content)
        sanitized_record = EvidenceRecord(
            id=record.id,
            source_type=record.source_type,
            content=sanitized_content,
            timestamp=record.timestamp,
            service=record.service,
            commit_id=record.commit_id,
            deployment_id=record.deployment_id,
            metadata=dict(record.metadata),
        )

        # Untrusted text inspection
        injections = inspect_for_prompt_injection(record.content)
        for inj in injections:
            self._warnings.append(f"Evidence '{record.id}': {inj}")

        self._records[sanitized_record.id] = sanitized_record

        # Update indexes
        if sanitized_record.service:
            self._service_index.setdefault(sanitized_record.service, set()).add(sanitized_record.id)
        if sanitized_record.commit_id:
            self._commit_index.setdefault(sanitized_record.commit_id, set()).add(sanitized_record.id)
        if sanitized_record.deployment_id:
            self._deployment_index.setdefault(sanitized_record.deployment_id, set()).add(sanitized_record.id)

    def get(self, evidence_id: str) -> Optional[EvidenceRecord]:
        return self._records.get(evidence_id)

    def contains(self, evidence_id: str) -> bool:
        return evidence_id in self._records

    @property
    def known_ids(self) -> Set[str]:
        return set(self._records.keys())

    def all_records(self) -> List[EvidenceRecord]:
        return list(self._records.values())

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    def find_by_service(self, service: str) -> List[EvidenceRecord]:
        ids = self._service_index.get(service, set())
        return [self._records[eid] for eid in ids]

    def find_by_commit(self, commit_id: str) -> List[EvidenceRecord]:
        ids = self._commit_index.get(commit_id, set())
        return [self._records[eid] for eid in ids]

    def find_by_deployment(self, deployment_id: str) -> List[EvidenceRecord]:
        ids = self._deployment_index.get(deployment_id, set())
        return [self._records[eid] for eid in ids]

    def verify_citations(self, evidence_ids: List[str]) -> Tuple[bool, List[str]]:
        """Verify that all evidence IDs exist in the store."""
        missing = [eid for eid in evidence_ids if eid not in self._records]
        if missing:
            return False, [f"Evidence ID not found: {eid}" for eid in missing]
        return True, []

    def evaluate_claim_support(self, claim: str, evidence_ids: List[str]) -> Dict[str, Any]:
        """Evaluate whether cited evidence provides grounding for a claim.

        Performs deterministic keyword overlap and n-gram lexical overlap
        between the claim and cited evidence text.
        """
        valid, missing_errs = self.verify_citations(evidence_ids)
        if not valid:
            return {
                "supported": False,
                "score": 0.0,
                "reason": "; ".join(missing_errs),
                "citation_valid": False,
            }

        # Extract meaningful terms from claim (excluding common stop words)
        stop_words = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
            "is", "was", "are", "were", "be", "been", "being", "with", "as", "by",
            "that", "this", "it", "not", "from", "has", "have", "had", "will"
        }
        claim_words = {
            w.lower()
            for w in re.findall(r"\b[A-Za-z0-9_]{3,}\b", claim)
            if w.lower() not in stop_words
        }

        if not claim_words:
            return {
                "supported": True,
                "score": 0.5,
                "reason": "Claim is generic or non-lexical.",
                "citation_valid": True,
            }

        matched_evidence = 0
        total_overlap = 0

        for eid in evidence_ids:
            rec = self._records[eid]
            evidence_words = {
                w.lower()
                for w in re.findall(r"\b[A-Za-z0-9_]{3,}\b", rec.content)
            }
            overlap = claim_words.intersection(evidence_words)
            if overlap:
                matched_evidence += 1
                total_overlap += len(overlap)

        if matched_evidence == 0:
            return {
                "supported": False,
                "score": 0.0,
                "reason": "None of the cited evidence records contain words related to the claim.",
                "citation_valid": True,
            }

        score = min(1.0, (matched_evidence / len(evidence_ids)) * (total_overlap / max(1, len(claim_words))))
        return {
            "supported": True,
            "score": round(score, 2),
            "reason": f"Overlap found in {matched_evidence}/{len(evidence_ids)} citations.",
            "citation_valid": True,
        }

    def to_list(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._records.values()]

    @classmethod
    def from_list(cls, data: List[Dict[str, Any]]) -> EvidenceStore:
        if not isinstance(data, list):
            raise ValidationError("Evidence data must be a list of records.")
        records = [EvidenceRecord.from_dict(item) for item in data]
        return cls(records)

    @classmethod
    def from_file(cls, path: str | Path) -> EvidenceStore:
        with Path(path).open(encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_list(data)

"""Append-only evidence ledger with stable IDs, excerpt bounds, and secret redaction."""

from __future__ import annotations

import hashlib

from patchproof.core.enums import EvidenceKind, TrustLevel
from patchproof.core.models import EvidenceItem, utc_now_iso
from patchproof.core.redaction import redact_secrets


def compute_sha256(text: str) -> str:
    """Compute a sha256:<hex> digest for the given text."""
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"


class EvidenceLedger:
    """Append-only evidence ledger for a single PatchProof verification run."""

    def __init__(self, max_excerpt_bytes: int = 4096) -> None:
        if max_excerpt_bytes < 64:
            raise ValueError("max_excerpt_bytes must be >= 64")
        self._max_excerpt_bytes = max_excerpt_bytes
        self._items: list[EvidenceItem] = []
        self._by_id: dict[str, EvidenceItem] = {}
        self._warnings: list[str] = []

    def append(
        self,
        *,
        kind: EvidenceKind,
        source_uri: str,
        content: str,
        trust_level: TrustLevel,
        path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        observed_at: str | None = None,
    ) -> EvidenceItem:
        """Append a new immutable EvidenceItem and return it."""
        redacted_text, was_redacted = redact_secrets(content)
        encoded = redacted_text.encode("utf-8", errors="replace")
        truncated_excerpt = False
        if len(encoded) > self._max_excerpt_bytes:
            excerpt = (
                encoded[: self._max_excerpt_bytes].decode("utf-8", errors="ignore")
                + "\n...[TRUNCATED]"
            )
            truncated_excerpt = True
        else:
            excerpt = redacted_text

        next_index = len(self._items) + 1
        evidence_id = f"E-{next_index:03d}"

        meta: dict[str, str | int | float | bool | None] = {}
        if metadata:
            for k, v in list(metadata.items())[:20]:
                if isinstance(v, (str, int, float, bool)) or v is None:
                    meta[str(k)[:64]] = v[:256] if isinstance(v, str) else v
        if truncated_excerpt:
            meta["excerpt_truncated"] = True

        item = EvidenceItem(
            evidence_id=evidence_id,
            kind=kind,
            source_uri=source_uri,
            path=path,
            line_start=line_start,
            line_end=line_end,
            content_excerpt=excerpt,
            content_hash=compute_sha256(redacted_text),
            observed_at=observed_at or utc_now_iso(),
            trust_level=trust_level,
            redacted=was_redacted,
            metadata=meta,
        )
        self._items.append(item)
        self._by_id[evidence_id] = item
        if was_redacted:
            self._warnings.append(
                f"Secret pattern redacted in evidence item {evidence_id} ({source_uri})"
            )
        return item

    def get(self, evidence_id: str) -> EvidenceItem | None:
        """Look up an evidence item by ID."""
        return self._by_id.get(evidence_id)

    def require(self, evidence_id: str) -> EvidenceItem:
        """Look up an evidence item by ID or raise KeyError."""
        item = self._by_id.get(evidence_id)
        if item is None:
            raise KeyError(f"Unknown evidence_id: {evidence_id}")
        return item

    def has(self, evidence_id: str) -> bool:
        """Return True if evidence_id exists in the ledger."""
        return evidence_id in self._by_id

    def items(self) -> list[EvidenceItem]:
        """Return a shallow copy of all recorded evidence items."""
        return list(self._items)

    def warnings(self) -> list[str]:
        """Return redaction or truncation warnings recorded by the ledger."""
        return list(self._warnings)

    def __len__(self) -> int:
        return len(self._items)


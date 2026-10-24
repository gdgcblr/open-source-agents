"""Universal Canonical Member Resolution Indexer.

Eliminates ID fragmentation by folding Firebase UIDs, internal IDs, and phone numbers
into a single canonical Member ID in O(1) time.
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional
from .models import Member


def clean_phone_digits(raw: str) -> str:
    """Normalizes phone numbers to standard format (+91XXXXXXXXXX or clean digits)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    if raw.startswith("+"):
        return f"+{digits}"
    return digits


def build_canonical_member_index(members: List[Member]) -> Dict[str, str]:
    """Builds an O(1) canonical resolution index across all identifier variants."""
    index: Dict[str, str] = {}
    for m in members:
        # Direct ID
        index[m.id] = m.id
        # Name lookup (case-insensitive)
        index[f"name_{m.name.strip().lower()}"] = m.id
        # Firebase Auth UID
        if m.uid:
            index[m.uid] = m.id
        # Phone numbers (full, normalized, and 10-digit suffix)
        if m.phone_number:
            clean = clean_phone_digits(m.phone_number)
            if clean:
                index[clean] = m.id
            raw_digits = re.sub(r"\D", "", m.phone_number)
            if raw_digits:
                index[raw_digits] = m.id
                if len(raw_digits) >= 10:
                    index[raw_digits[-10:]] = m.id
    return index


def resolve_canonical_member_id(
    raw_id: str,
    members: List[Member],
    index: Optional[Dict[str, str]] = None,
) -> str:
    """Resolves any raw identifier to the canonical Member.id."""
    if not raw_id:
        return raw_id
    lookup = index if index is not None else build_canonical_member_index(members)
    # Direct hash match
    if raw_id in lookup:
        return lookup[raw_id]
    # Name match
    name_key = f"name_{raw_id.strip().lower()}"
    if name_key in lookup:
        return lookup[name_key]
    # Clean phone match
    clean_phone = clean_phone_digits(raw_id)
    if clean_phone and clean_phone in lookup:
        return lookup[clean_phone]
    return raw_id

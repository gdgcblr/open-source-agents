"""Egress guardrail: last check on any text about to leave the machine.

Two independent checks, so one failing does not open a hole:
1. Vault tripwire: does the text contain any real value already hidden in this session?
   (Catches a bug or bypass that would re-introduce known PII.)
2. Fresh detection: does it contain a checksum-valid / labelled identifier that the active
   profile says must be hidden? (Catches PII that never went through Aran at all.)

Results report types and tokens only. The leaked values themselves are never returned,
logged or printed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aran import detectors, profiles
from aran.vault import Vault

# Short values ("Ravi") are too collision-prone to block on.
_MIN_TRIPWIRE_LEN = 5


@dataclass(frozen=True)
class Leak:
    type: str
    check: str  # "vault" | "detector"
    token: str | None = None


def _norm(s: str) -> str:
    return re.sub(r"[\s-]", "", s).casefold()


def find_leaks(text: str, session_id: str | None, profile: str = "kyc") -> list[Leak]:
    if not text:
        return []
    leaks: list[Leak] = []
    if session_id:
        flat = _norm(text)
        for token, entry in Vault(session_id).tokens.items():
            value = _norm(entry["value"])
            if len(value) >= _MIN_TRIPWIRE_LEN and value in flat:
                leaks.append(Leak(entry["type"], "vault", token))
    prof = profiles.load(profile)
    for f in detectors.detect(text):
        if prof.action_for(f.type) != "keep" and (f.validated or f.type in _HIGH_RISK):
            leaks.append(Leak(f.type, "detector"))
    return leaks


# Identifiers that are dangerous even without a checksum.
_HIGH_RISK = {"PAN", "AADHAAR", "CARD", "ACCOUNT_NUMBER", "GSTIN"}


def describe(leaks: list[Leak]) -> str:
    return ", ".join(sorted({f"{l.type} ({l.check})" for l in leaks}))

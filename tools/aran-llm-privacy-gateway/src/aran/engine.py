"""Core pipeline: detect -> apply profile (mask / generalise / keep) -> vault -> audit.

The output of redact_* is the only thing that should ever be sent to a cloud model.
restore() runs locally on the model's answer to put real values back.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from aran import audit, detectors, local_llm, profiles, readers
from aran.detectors import Finding
from aran.vault import Vault, open_session


@dataclass
class RedactionResult:
    session_id: str
    profile: str
    kind: str
    redacted: str
    findings: list[dict] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total_found(self) -> int:
        return sum(self.counts.get("found", {}).values())


def _preview(pii_type: str, value: str) -> str:
    """A safe-to-display hint of the value, for local reports only."""
    v = value.strip()
    if pii_type in {"PERSON", "ADDRESS", "ORG"}:
        return v[0] + "***" if v else "***"
    if pii_type == "EMAIL":
        user, _, domain = v.partition("@")
        return f"{user[:1]}***@{domain}"
    return "*" * max(len(v) - 4, 0) + v[-4:]


_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y")


def _age_band(value: str, today: date | None = None) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            born = datetime.strptime(value.strip(), fmt).date()
            break
        except ValueError:
            continue
    else:
        return None
    today = today or date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    lo = age // 5 * 5
    return f"[age {lo}-{lo + 4}]"


def _llm_findings(text: str, vault: Vault) -> list[Finding]:
    """Names/addresses from the local model, plus every name already seen in this session."""
    wanted: dict[str, str] = {t: k for t, k in local_llm.find_entities(text)}
    for entry in vault.tokens.values():
        if entry["type"] in local_llm.NER_TYPES:
            wanted.setdefault(entry["value"], entry["type"])
    out: list[Finding] = []
    for needle, kind in wanted.items():
        for m in re.finditer(rf"(?<!\w){re.escape(needle)}(?!\w)", text, flags=re.IGNORECASE):
            out.append(Finding(m.start(), m.end(), kind, m.group(0), "llm"))
    return out


def _apply(text: str, findings: list[Finding], profile: profiles.Profile, vault: Vault):
    counts = {k: Counter() for k in ("found", "masked", "generalised", "kept")}
    report: list[dict] = []
    pieces: list[str] = []
    cursor = 0
    for f in findings:
        action = profile.action_for(f.type)
        replacement = f.value
        if action == "age_band":
            band = _age_band(f.value)
            if band:
                replacement = band
            else:
                action = "mask"  # unparseable date: fail closed
        if action == "mask":
            replacement = vault.token_for(f.type, f.value)
        bucket = {"mask": "masked", "age_band": "generalised", "keep": "kept"}[action]
        counts["found"][f.type] += 1
        counts[bucket][f.type] += 1
        report.append({
            "type": f.type,
            "action": action,
            "replacement": replacement if action != "keep" else None,
            "preview": _preview(f.type, f.value),
            "checksum_valid": f.validated,
            "detector": f.source,
        })
        pieces.append(text[cursor:f.start])
        pieces.append(replacement)
        cursor = f.end
    pieces.append(text[cursor:])
    return "".join(pieces), report, {k: dict(v) for k, v in counts.items()}


_OCR_KINDS = {"image", "scanned_pdf"}


def _redact(text: str, profile: profiles.Profile, vault: Vault, use_llm: bool, kind: str):
    findings = detectors.detect(text, ocr=kind in _OCR_KINDS)
    if use_llm:
        findings = detectors.resolve_overlaps(findings + _llm_findings(text, vault))
    return _apply(text, findings, profile, vault)


def redact_text(
    text: str,
    profile: str = "kyc",
    session_id: str | None = None,
    *,
    use_llm: bool = True,
    channel: str = "python",
    kind: str = "text",
) -> RedactionResult:
    prof = profiles.load(profile)
    with open_session(session_id) as vault:
        redacted, report, counts = _redact(text, prof, vault, use_llm, kind)
    audit.record(session_id=vault.session_id, content=text, kind=kind, profile=prof.name,
                 counts=counts, channel=channel)
    return RedactionResult(vault.session_id, prof.name, kind, redacted, report, counts)


# Column headers whose whole cell is a person or an address.
_PERSON_COL = re.compile(r"(?i)name|customer|applicant|patient|father|mother|spouse|nominee|holder")
_ADDRESS_COL = re.compile(r"(?i)address|addr\b|street|locality")
_NOT_PERSON_COL = re.compile(r"(?i)bank|branch|company|employer|hospital|merchant|file|product|lab")


def _column_type(header: str) -> str | None:
    if _ADDRESS_COL.search(header):
        return "ADDRESS"
    if _PERSON_COL.search(header) and not _NOT_PERSON_COL.search(header):
        return "PERSON"
    return None


def _redact_table(df: pd.DataFrame, prof: profiles.Profile, vault: Vault):
    out = df.copy()
    report: list[dict] = []
    counts = {k: Counter() for k in ("found", "masked", "generalised", "kept")}
    for col in df.columns:
        whole = _column_type(str(col))
        for i, cell in df[col].items():
            if not cell.strip():
                continue
            if whole:
                findings = [Finding(0, len(cell), whole, cell, "column")]
            else:
                findings = detectors.detect(cell)
            if not findings:
                continue
            new, rep, c = _apply(cell, findings, prof, vault)
            out.at[i, col] = new
            report.extend(rep)
            for k in counts:
                counts[k].update(c[k])
    return out.to_csv(index=False), report, {k: dict(v) for k, v in counts.items()}


def redact_document(
    path: str | Path,
    profile: str = "kyc",
    session_id: str | None = None,
    *,
    use_llm: bool = True,
    channel: str = "python",
) -> RedactionResult:
    path = Path(path)
    prof = profiles.load(profile)
    doc = readers.read(path)  # slow OCR happens outside the vault lock
    with open_session(session_id) as vault:
        if doc.kind == "table":
            content = doc.table.to_csv(index=False)
            redacted, report, counts = _redact_table(doc.table, prof, vault)
        else:
            content = doc.text
            redacted, report, counts = _redact(doc.text, prof, vault, use_llm, doc.kind)
    audit.record(session_id=vault.session_id, content=content, kind=doc.kind, profile=prof.name,
                 counts=counts, channel=channel)
    return RedactionResult(vault.session_id, prof.name, doc.kind, redacted, report, counts)


def restore(text: str, session_id: str) -> str:
    """Put real values back into text produced from redacted input. Local use only."""
    return Vault(session_id).restore(text)

"""SQLite review gate; model proposals can never approve themselves."""

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .models import Kind, Proposal, SourceNote


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def guardrails(proposal: Proposal, note: SourceNote) -> list[str]:
    flags = []
    if proposal.currency != "INR":
        flags.append("unsupported_currency")
    if proposal.kind == Kind.UNKNOWN:
        flags.append("unknown_direction")
    if proposal.confidence < 0.8:
        flags.append("low_confidence")
    if proposal.evidence not in note.text:
        flags.append("evidence_not_in_source")
    numbers = re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d{1,2})?(?![\w.])", proposal.evidence)
    if proposal.amount not in [Decimal(value.replace(",", "")) for value in numbers]:
        flags.append("amount_not_in_evidence")
    return flags


class Ledger:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL,
                    explanation TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, note_id TEXT NOT NULL REFERENCES notes(id),
                    original TEXT NOT NULL, proposal TEXT NOT NULL,
                    flags TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    reviewer_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL,
                    action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def add_note(self, note: SourceNote) -> tuple[str, bool]:
        payload = note.model_dump_json()
        note_id = digest(f"{note.source}:{note.source_id}:{note.text}")
        with self.connect() as connection:
            result = connection.execute(
                "INSERT OR IGNORE INTO notes(id,payload,state,created_at) VALUES (?,?,?,?)",
                (note_id, payload, "queued", timestamp()),
            )
        return note_id, result.rowcount == 1

    def stage(self, note_id: str, proposals: list[Proposal], explanation: str) -> None:
        with self.connect() as connection:
            note_row = connection.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            if not note_row:
                raise ValueError("Source note not found")
            if note_row["state"] == "processed":
                return
            note = SourceNote.model_validate_json(note_row["payload"])
            for number, proposal in enumerate(proposals):
                candidate_id = digest(f"{note_id}:{number}")
                payload = proposal.model_dump_json()
                connection.execute(
                    "INSERT OR IGNORE INTO candidates"
                    "(id,note_id,original,proposal,flags,created_at) VALUES (?,?,?,?,?,?)",
                    (candidate_id, note_id, payload, payload,
                     json.dumps(guardrails(proposal, note)), timestamp()),
                )
            connection.execute(
                "UPDATE notes SET state='processed', explanation=? WHERE id=?",
                (explanation, note_id),
            )

    def mark_error(self, note_id: str, message: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE notes SET state='error', explanation=? WHERE id=?",
                               (message[:500], note_id))

    def queued_notes(self) -> list[tuple[str, SourceNote]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM notes WHERE state IN ('queued','error')").fetchall()
        return [(row["id"], SourceNote.model_validate_json(row["payload"])) for row in rows]

    def snapshot(self) -> dict:
        with self.connect() as connection:
            notes = [dict(row) for row in connection.execute("SELECT * FROM notes ORDER BY created_at DESC")]
            candidates = [dict(row) for row in connection.execute("SELECT * FROM candidates ORDER BY created_at DESC")]
            audit = [dict(row) for row in connection.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]
        note_map = {row["id"]: row for row in notes}
        for row in notes:
            row["payload"] = json.loads(row["payload"])
        for row in candidates:
            row["proposal"] = json.loads(row["proposal"])
            row["original"] = json.loads(row["original"])
            row["flags"] = json.loads(row["flags"])
            row["source"] = note_map[row["note_id"]]["payload"]
        return {"notes": notes, "candidates": candidates, "audit": audit}

    def review(self, candidate_id: str, action: str, reviewer_note: str,
               corrected: Proposal | None = None, confirm_duplicate: bool = False) -> None:
        if action not in {"approved", "rejected"} or len(reviewer_note.strip()) < 5:
            raise ValueError("Approval/rejection requires a review note of at least five characters")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            if not row:
                raise ValueError("Transaction not found")
            if row["status"] != "pending":
                raise ValueError("Transaction was already reviewed")
            proposal = corrected or Proposal.model_validate_json(row["proposal"])
            note_row = connection.execute("SELECT payload FROM notes WHERE id=?", (row["note_id"],)).fetchone()
            flags = guardrails(proposal, SourceNote.model_validate_json(note_row["payload"]))
            blocking = {"unsupported_currency", "unknown_direction", "evidence_not_in_source", "amount_not_in_evidence"}
            if action == "approved" and blocking.intersection(flags):
                raise ValueError("Resolve blocking guardrails before approval: " + ", ".join(flags))
            existing = connection.execute("SELECT proposal FROM candidates WHERE status='approved'").fetchall()
            duplicate = any(
                (other.transaction_date, other.amount, other.currency) ==
                (proposal.transaction_date, proposal.amount, proposal.currency)
                for other in (Proposal.model_validate_json(item["proposal"]) for item in existing)
            )
            if action == "approved" and duplicate and not confirm_duplicate:
                raise ValueError("Possible duplicate: same date, amount and currency. Confirm it is a distinct transaction.")
            connection.execute(
                "UPDATE candidates SET proposal=?, flags=?, status=?, reviewer_note=? WHERE id=?",
                (proposal.model_dump_json(), json.dumps(flags), action, reviewer_note.strip(), candidate_id),
            )
            connection.execute("INSERT INTO audit(candidate_id,action,detail,created_at) VALUES (?,?,?,?)",
                               (candidate_id, action, json.dumps({"reviewer_note": reviewer_note.strip(),
                                "before": json.loads(row["proposal"]), "after": proposal.model_dump(mode="json"),
                                "confirmed_distinct": confirm_duplicate}), timestamp()))

    def monthly(self, month: str) -> dict:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError("Month must be YYYY-MM")
        totals = {kind.value: Decimal("0") for kind in Kind}
        categories: dict[str, Decimal] = {}
        count = 0
        for row in self.snapshot()["candidates"]:
            proposal = Proposal.model_validate(row["proposal"])
            if row["status"] != "approved" or proposal.transaction_date.isoformat()[:7] != month:
                continue
            totals[proposal.kind.value] += proposal.amount
            if proposal.kind == Kind.SPENDING:
                categories[proposal.category] = categories.get(proposal.category, Decimal("0")) + proposal.amount
            count += 1
        inflow = totals["income"] + totals["borrowing"] + totals["repayment_received"]
        outflow = totals["spending"] + totals["lending"] + totals["repayment_paid"]
        return {"month": month, "currency": "INR", "approved_count": count,
                "totals": {key: str(value) for key, value in totals.items()},
                "categories": {key: str(value) for key, value in categories.items()},
                "net_cashflow": str(inflow - outflow)}
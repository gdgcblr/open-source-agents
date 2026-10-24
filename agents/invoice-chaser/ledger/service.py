"""The Ledger: the only component that reads or writes storage.

Every public method returns JSON-friendly dicts and is a candidate tool for
the agents. Permissions are bound at construction (`actor`), never taken from
the caller's arguments, so an LLM cannot claim to be the owner.
"""

import csv
import functools
import hashlib
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from ledger import ageing, invariants, matching, render, states
from ledger.config import LedgerConfig
from ledger.db import connect
from ledger.errors import LedgerError
from ledger.parsing import format_date, format_money, parse_amount, parse_date
from ledger.policy import policy_reasons

ACTORS = ("owner", "agent")
LANGUAGES = ("en", "hinglish")
MAX_INVOICES_PER_MATCH = 5


def owner_only(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.actor != "owner":
            raise LedgerError("FORBIDDEN", f"{method.__name__} can only be done by the owner")
        return method(self, *args, **kwargs)

    wrapper.owner_only = True
    return wrapper


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_csv(path: str | Path) -> list[dict]:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in rows]


def _require_columns(rows: list[dict], required: set[str], path) -> None:
    present = set(rows[0].keys()) if rows else set()
    if missing := required - present:
        raise LedgerError("IMPORT_INVALID", f"{Path(path).name}: missing columns {sorted(missing)}",
                          errors=[f"missing column: {c}" for c in sorted(missing)])


def _flags(raw: str) -> set[str]:
    return {f.strip() for f in raw.split(";") if f.strip()}


class Ledger:
    def __init__(self, db_path: str | Path, config: LedgerConfig | None = None,
                 actor: str = "owner"):
        if actor not in ACTORS:
            raise ValueError(f"actor must be one of {ACTORS}")
        self.config = config or LedgerConfig()
        self.actor = actor
        self.conn = connect(db_path)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ infra

    @contextmanager
    def _tx(self):
        """One transaction per write. Invariants are checked before commit."""
        try:
            yield
            if violations := invariants.check(self.conn, self.config):
                raise LedgerError("INVARIANT_VIOLATION", "write would break ledger invariants",
                                  violations=violations)
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def _audit(self, action: str, entity: str, entity_id, details: dict | None = None,
               run_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit (ts, run_id, actor, action, entity, entity_id, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), run_id, self.actor, action, entity, str(entity_id),
             json.dumps(details or {}, ensure_ascii=False)))

    def _as_of(self, as_of: str | None = None) -> date:
        return date.fromisoformat(as_of) if as_of else self.config.today()

    # ---------------------------------------------------------------- imports

    @owner_only
    def import_clients(self, path: str) -> dict:
        rows = _read_csv(path)
        _require_columns(rows, {"client_id", "name", "contact_name", "email", "language"}, path)
        errors, records = [], []
        for n, row in enumerate(rows, start=2):
            if not row["client_id"] or not row["name"] or not row["contact_name"]:
                errors.append(f"row {n}: client_id, name and contact_name are required")
            elif row["language"] not in LANGUAGES:
                errors.append(f"row {n}: language must be one of {LANGUAGES}")
            else:
                records.append((row["client_id"], row["name"], row["contact_name"], row["email"],
                                row["language"], ";".join(sorted(_flags(row.get("flags", ""))))))
        return self._insert_idempotent("clients", records, errors,
                                       "id, name, contact_name, email, language, flags")

    @owner_only
    def import_invoices(self, path: str) -> dict:
        rows = _read_csv(path)
        _require_columns(rows, {"invoice_no", "client_id", "issue_date", "due_date", "amount"}, path)
        known_clients = {r[0] for r in self.conn.execute("SELECT id FROM clients")}
        errors, warnings, records, seen = [], [], [], set()
        for n, row in enumerate(rows, start=2):
            try:
                inv_no = row["invoice_no"]
                if not inv_no:
                    raise ValueError("invoice_no is required")
                if inv_no in seen:
                    raise ValueError(f"duplicate invoice_no {inv_no} in file")
                seen.add(inv_no)
                if row["client_id"] not in known_clients:
                    raise ValueError(f"unknown client_id {row['client_id']!r} (import clients first)")
                issue, amb1 = parse_date(row["issue_date"], self.config.day_first)
                due, amb2 = parse_date(row["due_date"], self.config.day_first)
                if due < issue:
                    raise ValueError("due_date is before issue_date")
                amount = parse_amount(row["amount"])
                if amount <= 0:
                    raise ValueError("amount must be positive")
                if amb1 or amb2:
                    order = "DD/MM" if self.config.day_first else "MM/DD"
                    warnings.append(f"row {n}: ambiguous date read as {order}")
                records.append((inv_no, row["client_id"], (row.get("currency") or "INR").upper(),
                                amount, issue.isoformat(), due.isoformat(),
                                row.get("description", "")))
            except ValueError as e:
                errors.append(f"row {n}: {e}")
        result = self._insert_idempotent(
            "invoices", records, errors,
            "id, client_id, currency, amount_paise, issue_date, due_date, description")
        result["warnings"] = warnings
        return result

    def _insert_idempotent(self, table: str, records: list[tuple], errors: list[str],
                           columns: str) -> dict:
        """All-or-nothing. Identical existing rows are skipped; conflicting ones are errors."""
        cols = [c.strip() for c in columns.split(",")]
        new, unchanged = [], 0
        for rec in records:
            existing = self.conn.execute(f"SELECT {columns} FROM {table} WHERE id = ?",
                                         (rec[0],)).fetchone()
            if existing is None:
                new.append(rec)
            elif tuple(existing) == rec:
                unchanged += 1
            else:
                diff = [c for c, a, b in zip(cols, existing, rec) if a != b]
                errors.append(f"{rec[0]}: already exists with different {', '.join(diff)}")
        if errors:
            raise LedgerError("IMPORT_INVALID", f"{len(errors)} problem(s); nothing imported",
                              errors=errors)
        with self._tx():
            placeholders = ", ".join("?" for _ in cols)
            for rec in new:
                self.conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rec)
                self._audit("import", table.rstrip("s"), rec[0])
        return {"ok": True, "imported": len(new), "unchanged": unchanged}

    @owner_only
    def import_payments(self, path: str, currency: str = "INR") -> dict:
        """Bank statement CSV with columns: date, narration, ref, credit, debit [, currency]."""
        rows = _read_csv(path)
        _require_columns(rows, {"date", "narration", "credit"}, path)
        errors, records, debits = [], [], 0
        for n, row in enumerate(rows, start=2):
            try:
                if not row.get("credit"):
                    if row.get("debit"):
                        debits += 1
                        continue
                    raise ValueError("neither credit nor debit")
                txn_date, _ = parse_date(row["date"], self.config.day_first)
                amount = parse_amount(row["credit"])
                if amount <= 0:
                    raise ValueError("credit must be positive")
                cur = (row.get("currency") or currency).upper()
                key = hashlib.sha256(
                    f"{txn_date}|{amount}|{cur}|{row.get('ref', '')}|{row['narration']}".encode()
                ).hexdigest()[:24]
                records.append((txn_date.isoformat(), amount, cur, row["narration"],
                                row.get("ref", ""), key))
            except ValueError as e:
                errors.append(f"row {n}: {e}")
        if errors:
            raise LedgerError("IMPORT_INVALID", f"{len(errors)} problem(s); nothing imported",
                              errors=errors)
        imported = duplicates = 0
        with self._tx():
            for rec in records:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO payments (txn_date, amount_paise, currency, narration, "
                    "ref, dedupe_key) VALUES (?, ?, ?, ?, ?, ?)", rec)
                if cur.rowcount:
                    imported += 1
                    self._audit("import", "payment", cur.lastrowid)
                else:
                    duplicates += 1
        return {"ok": True, "imported": imported, "duplicates_skipped": duplicates,
                "debits_ignored": debits}

    # ------------------------------------------------------------------ reads

    def _settled(self, invoice_id: str) -> tuple[int, bool]:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(paid_paise + tds_paise), 0), COUNT(*) FROM allocations "
            "WHERE invoice_id = ?", (invoice_id,)).fetchone()
        return row[0], row[1] > 0

    def _invoice_row(self, invoice_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT i.*, c.name AS client_name, c.contact_name, c.language, c.flags "
            "FROM invoices i JOIN clients c ON c.id = i.client_id WHERE i.id = ?",
            (invoice_id,)).fetchone()
        if row is None:
            raise LedgerError("UNKNOWN_INVOICE", f"No invoice {invoice_id!r}")
        return row

    def _invoice_view(self, row: sqlite3.Row, as_of: date) -> dict:
        settled, has_payments = self._settled(row["id"])
        due = date.fromisoformat(row["due_date"])
        status = states.invoice_status(
            amount=row["amount_paise"], settled=settled, hold=row["hold"], due=due, as_of=as_of,
            heads_up_days=self.config.heads_up_days, tolerance=self.config.tolerance_paise)
        outstanding = max(row["amount_paise"] - settled, 0)
        overdue = ageing.days_overdue(due, as_of)
        return {
            "invoice_id": row["id"], "client_id": row["client_id"],
            "client_name": row["client_name"], "currency": row["currency"],
            "amount": format_money(row["amount_paise"], row["currency"]),
            "outstanding": format_money(outstanding, row["currency"]),
            "outstanding_paise": outstanding, "has_payments": has_payments,
            "issue_date": row["issue_date"], "due_date": row["due_date"],
            "days_overdue": overdue, "bucket": ageing.bucket(overdue), "status": status,
            "description": row["description"],
        }

    def get_invoice(self, invoice_id: str, as_of: str | None = None) -> dict:
        return {"ok": True, "invoice": self._invoice_view(self._invoice_row(invoice_id),
                                                          self._as_of(as_of))}

    def list_open_invoices(self, client_id: str | None = None, as_of: str | None = None) -> dict:
        today = self._as_of(as_of)
        sql = ("SELECT i.*, c.name AS client_name, c.contact_name, c.language, c.flags "
               "FROM invoices i JOIN clients c ON c.id = i.client_id")
        params: tuple = ()
        if client_id:
            sql, params = sql + " WHERE i.client_id = ?", (client_id,)
        views = [self._invoice_view(r, today) for r in self.conn.execute(sql + " ORDER BY i.due_date", params)]
        return {"ok": True, "as_of": today.isoformat(),
                "invoices": [v for v in views if v["status"] in states.OPEN_STATUSES]}

    def list_unmatched_payments(self) -> dict:
        rows = self.conn.execute(
            "SELECT id, txn_date, amount_paise, currency, narration, ref FROM payments "
            "WHERE status = 'UNMATCHED' ORDER BY txn_date, id").fetchall()
        return {"ok": True, "payments": [
            {"payment_id": r["id"], "date": r["txn_date"], "currency": r["currency"],
             "amount": format_money(r["amount_paise"], r["currency"]),
             # Narration is untrusted bank data. It is labelled so prompts can treat it as data.
             "narration_untrusted": r["narration"], "ref": r["ref"]} for r in rows]}

    def get_client_context(self, client_id: str, as_of: str | None = None) -> dict:
        c = self.conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if c is None:
            raise LedgerError("UNKNOWN_CLIENT", f"No client {client_id!r}")
        reminders = self.conn.execute(
            "SELECT r.id, r.invoice_id, r.tone_level, r.status, r.sent_on, r.created_at "
            "FROM reminders r JOIN invoices i ON i.id = r.invoice_id WHERE i.client_id = ? "
            "AND r.status NOT IN ('DROPPED') ORDER BY r.id DESC LIMIT 3", (client_id,)).fetchall()
        flags = _flags(c["flags"])
        return {"ok": True, "client": {
            "client_id": c["id"], "name": c["name"], "contact_name": c["contact_name"],
            "language": c["language"], "flags": sorted(flags),
            "max_tone_level": ageing.tone_cap(flags)},
            "open_invoices": self.list_open_invoices(client_id, as_of)["invoices"],
            "recent_reminders": [dict(r) for r in reminders]}

    def _reminder_history(self, invoice_id: str) -> tuple[bool, date | None, int | None]:
        pending = self.conn.execute(
            "SELECT 1 FROM reminders WHERE invoice_id = ? AND status IN ('QUEUED', 'APPROVED')",
            (invoice_id,)).fetchone() is not None
        row = self.conn.execute(
            "SELECT MAX(sent_on), MAX(tone_level) FROM reminders WHERE invoice_id = ? "
            "AND sent_on IS NOT NULL", (invoice_id,)).fetchone()
        last_sent = date.fromisoformat(row[0]) if row[0] else None
        return pending, last_sent, row[1]

    @staticmethod
    def _validate_tone_language(tone_level, language: str | None = None) -> None:
        if tone_level not in (0, 1, 2, 3) or isinstance(tone_level, bool):
            raise LedgerError("INVALID_REQUEST", "tone_level must be 0, 1, 2 or 3")
        if language is not None and language not in LANGUAGES:
            raise LedgerError("INVALID_REQUEST", f"language must be one of {LANGUAGES}")

    def check_policy(self, invoice_id: str, tone_level: int, as_of: str | None = None) -> dict:
        self._validate_tone_language(tone_level)
        today = self._as_of(as_of)
        row = self._invoice_row(invoice_id)
        view = self._invoice_view(row, today)
        pending, last_sent, _ = self._reminder_history(invoice_id)
        reasons = policy_reasons(
            status=view["status"], due=date.fromisoformat(row["due_date"]), as_of=today,
            tone_level=tone_level, flags=_flags(row["flags"]), pending_reminder=pending,
            last_sent_on=last_sent, config=self.config)
        return {"ok": True, "allowed": not reasons, "reasons": reasons}

    def get_chase_list(self, as_of: str | None = None) -> dict:
        """Open invoices that are due soon or overdue, highest priority first."""
        today = self._as_of(as_of)
        items = []
        for view in self.list_open_invoices(as_of=today.isoformat())["invoices"]:
            if -view["days_overdue"] > self.config.heads_up_days:
                continue
            row = self._invoice_row(view["invoice_id"])
            flags = _flags(row["flags"])
            _, _, last_tone = self._reminder_history(view["invoice_id"])
            tone = ageing.recommended_tone(view["days_overdue"], flags, last_tone)
            policy = self.check_policy(view["invoice_id"], tone, today.isoformat())
            items.append({
                **{k: view[k] for k in ("invoice_id", "client_id", "client_name", "currency",
                                        "outstanding", "due_date", "days_overdue", "bucket",
                                        "status")},
                "contact_name": row["contact_name"], "language": row["language"],
                "recommended_tone": tone,
                "priority": ageing.priority(view["outstanding_paise"], view["days_overdue"]),
                "can_queue_reminder": policy["allowed"], "policy_reasons": policy["reasons"],
            })
        items.sort(key=lambda i: i["priority"], reverse=True)
        return {"ok": True, "as_of": today.isoformat(), "items": items}

    # --------------------------------------------------------------- matching

    def _open_invoice(self, row: sqlite3.Row, today: date) -> matching.OpenInvoice:
        view = self._invoice_view(row, today)
        return matching.OpenInvoice(row["id"], row["client_id"], row["currency"],
                                    view["outstanding_paise"], view["has_payments"],
                                    row["due_date"])

    def propose_match(self, payment_id: int, invoice_ids: list[str], name_confidence: float,
                      reason: str, run_id: str | None = None) -> dict:
        """Propose that a payment settles one or more invoices.

        The ledger decides whether it is auto-applied or needs the owner's
        confirmation; the caller cannot force it.
        """
        today = self.config.today()
        if not isinstance(invoice_ids, list) or not invoice_ids:
            raise LedgerError("INVALID_REQUEST", "invoice_ids must be a non-empty list")
        if len(set(invoice_ids)) != len(invoice_ids) or len(invoice_ids) > MAX_INVOICES_PER_MATCH:
            raise LedgerError("INVALID_REQUEST",
                              f"invoice_ids must be unique and at most {MAX_INVOICES_PER_MATCH}")
        if not 0.0 <= float(name_confidence) <= 1.0:
            raise LedgerError("INVALID_REQUEST", "name_confidence must be between 0 and 1")
        if not str(reason).strip():
            raise LedgerError("INVALID_REQUEST", "reason is required")
        reason = str(reason).strip()[:500]

        pay = self.conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if pay is None:
            raise LedgerError("UNKNOWN_PAYMENT", f"No payment {payment_id!r}")
        if pay["status"] == "MATCHED":
            raise LedgerError("PAYMENT_ALREADY_MATCHED", f"Payment {payment_id} is already matched")

        proposed = []
        for inv_id in invoice_ids:
            row = self._invoice_row(inv_id)
            if self._invoice_view(row, today)["status"] not in states.OPEN_STATUSES:
                raise LedgerError("INVOICE_NOT_OPEN", f"Invoice {inv_id} is not open")
            if row["currency"] != pay["currency"]:
                raise LedgerError("CURRENCY_MISMATCH",
                                  f"Payment is {pay['currency']}, invoice {inv_id} is {row['currency']}")
            proposed.append(self._open_invoice(row, today))
        if len({i.client_id for i in proposed}) > 1:
            raise LedgerError("INVALID_REQUEST", "All invoices in one match must belong to one client")

        cfg = self.config
        sig = matching.amount_signal(pay["amount_paise"], proposed, cfg.tds_rates, cfg.tolerance_paise)
        if sig.signal == matching.MISMATCH:
            raise LedgerError("AMOUNT_MISMATCH",
                              "Payment amount does not equal the total (with or without TDS) "
                              "of these invoices")
        others = [self._open_invoice(self._invoice_row(v["invoice_id"]), today)
                  for v in self.list_open_invoices(as_of=today.isoformat())["invoices"]
                  if v["invoice_id"] not in invoice_ids]
        ambiguous = matching.find_ambiguity(pay["amount_paise"], proposed, others,
                                            cfg.tds_rates, cfg.tolerance_paise)
        decision = matching.decide(sig.signal, float(name_confidence), len(proposed), ambiguous,
                                   cfg.auto_apply_min_name_confidence)

        with self._tx():
            cur = self.conn.execute(
                "INSERT INTO match_proposals (payment_id, invoice_ids, signal, name_confidence, "
                "reason, decision, status, ambiguous_with, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)",
                (payment_id, json.dumps(invoice_ids), sig.signal, float(name_confidence), reason,
                 decision, json.dumps(ambiguous), run_id, _now()))
            proposal_id = cur.lastrowid
            self._audit("propose_match", "match_proposal", proposal_id,
                        {"payment_id": payment_id, "invoice_ids": invoice_ids,
                         "signal": sig.signal, "name_confidence": name_confidence,
                         "decision": decision, "ambiguous_with": ambiguous, "reason": reason},
                        run_id)
            if decision == matching.AUTO_APPLIED:
                self._apply(proposal_id, payment_id, sig, applied_by="auto", run_id=run_id)
            else:
                self.conn.execute("UPDATE payments SET status = 'PENDING_CONFIRMATION' "
                                  "WHERE id = ?", (payment_id,))

        return {"ok": True, "proposal_id": proposal_id, "decision": decision,
                "signal": sig.signal, "tds_rate": sig.tds_rate, "ambiguous_with": ambiguous,
                "allocations": [{"invoice_id": a.invoice_id,
                                 "paid": format_money(a.paid, pay["currency"]),
                                 "tds": format_money(a.tds, pay["currency"])} for a in sig.allocations],
                "unallocated": format_money(sig.unallocated, pay["currency"])}

    def _apply(self, proposal_id: int, payment_id: int, sig: matching.AmountSignal,
               applied_by: str, run_id: str | None) -> None:
        for a in sig.allocations:
            cur = self.conn.execute(
                "INSERT INTO allocations (payment_id, invoice_id, paid_paise, tds_paise, "
                "proposal_id, applied_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (payment_id, a.invoice_id, a.paid, a.tds, proposal_id, applied_by, _now()))
            self._audit("apply_allocation", "allocation", cur.lastrowid,
                        {"payment_id": payment_id, "invoice_id": a.invoice_id, "paid_paise": a.paid,
                         "tds_paise": a.tds, "applied_by": applied_by}, run_id)
            self._cancel_pending_reminders(a.invoice_id, "invoice_received_payment", run_id)
        self.conn.execute("UPDATE payments SET status = 'MATCHED' WHERE id = ?", (payment_id,))
        self.conn.execute("UPDATE match_proposals SET status = 'APPLIED' WHERE id = ?",
                          (proposal_id,))
        self.conn.execute("UPDATE match_proposals SET status = 'SUPERSEDED' WHERE payment_id = ? "
                          "AND status = 'PENDING'", (payment_id,))

    def _cancel_pending_reminders(self, invoice_id: str, why: str, run_id: str | None) -> None:
        for r in self.conn.execute("SELECT id FROM reminders WHERE invoice_id = ? AND status IN "
                                   "('QUEUED', 'APPROVED')", (invoice_id,)).fetchall():
            self.conn.execute("UPDATE reminders SET status = 'CANCELLED' WHERE id = ?", (r[0],))
            self._audit("cancel_reminder", "reminder", r[0], {"why": why}, run_id)

    def list_pending_matches(self) -> dict:
        rows = self.conn.execute(
            "SELECT m.*, p.amount_paise, p.currency, p.narration, p.txn_date FROM match_proposals m "
            "JOIN payments p ON p.id = m.payment_id WHERE m.status = 'PENDING' ORDER BY m.id"
        ).fetchall()
        return {"ok": True, "proposals": [
            {"proposal_id": r["id"], "payment_id": r["payment_id"], "date": r["txn_date"],
             "amount": format_money(r["amount_paise"], r["currency"]),
             "narration": r["narration"], "invoice_ids": json.loads(r["invoice_ids"]),
             "signal": r["signal"], "name_confidence": r["name_confidence"],
             "ambiguous_with": json.loads(r["ambiguous_with"]), "reason": r["reason"]}
            for r in rows]}

    def _pending_proposal(self, proposal_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM match_proposals WHERE id = ?",
                                (proposal_id,)).fetchone()
        if row is None:
            raise LedgerError("UNKNOWN_PROPOSAL", f"No proposal {proposal_id!r}")
        if row["status"] != "PENDING":
            raise LedgerError("ILLEGAL_TRANSITION", f"Proposal {proposal_id} is {row['status']}")
        return row

    @owner_only
    def confirm_match(self, proposal_id: int) -> dict:
        prop = self._pending_proposal(proposal_id)
        pay = self.conn.execute("SELECT * FROM payments WHERE id = ?",
                                (prop["payment_id"],)).fetchone()
        today = self.config.today()
        invoices = [self._open_invoice(self._invoice_row(i), today)
                    for i in json.loads(prop["invoice_ids"])]
        sig = matching.amount_signal(pay["amount_paise"], invoices, self.config.tds_rates,
                                     self.config.tolerance_paise)
        if sig.signal != prop["signal"]:
            raise LedgerError("STALE_PROPOSAL", "Invoices changed since this was proposed; re-run matching")
        with self._tx():
            self._apply(proposal_id, prop["payment_id"], sig, applied_by="owner", run_id=None)
            self._audit("confirm_match", "match_proposal", proposal_id)
        return {"ok": True, "proposal_id": proposal_id, "status": "APPLIED",
                "unallocated": format_money(sig.unallocated, pay["currency"])}

    @owner_only
    def reject_match(self, proposal_id: int) -> dict:
        prop = self._pending_proposal(proposal_id)
        with self._tx():
            self.conn.execute("UPDATE match_proposals SET status = 'REJECTED' WHERE id = ?",
                              (proposal_id,))
            still_pending = self.conn.execute(
                "SELECT 1 FROM match_proposals WHERE payment_id = ? AND status = 'PENDING'",
                (prop["payment_id"],)).fetchone()
            if not still_pending:
                self.conn.execute("UPDATE payments SET status = 'UNMATCHED' WHERE id = ?",
                                  (prop["payment_id"],))
            self._audit("reject_match", "match_proposal", proposal_id)
        return {"ok": True, "proposal_id": proposal_id, "status": "REJECTED"}

    # -------------------------------------------------------------- reminders

    def _render(self, invoice_id: str, tone_level: int, language: str, subject_template: str,
                body_template: str) -> dict:
        problems = []
        if tone_level not in (0, 1, 2, 3):
            problems.append("tone_level must be 0, 1, 2 or 3")
        if language not in LANGUAGES:
            problems.append(f"language must be one of {LANGUAGES}")
        if not str(subject_template).strip():
            problems.append("subject: empty")
        if not str(body_template).strip():
            problems.append("body: empty")
        for slot in ("{invoice_no}", "{amount_due}"):
            if slot not in body_template:
                problems.append(f"body: must include {slot}")
        level = tone_level if tone_level in (0, 1, 2, 3) else 0
        problems += render.template_problems(subject_template, level, "subject")
        problems += render.template_problems(body_template, level, "body")
        if problems:
            raise LedgerError("RENDER_REJECTED", "Template rejected; fix and retry",
                              problems=problems)

        row = self._invoice_row(invoice_id)
        view = self._invoice_view(row, self.config.today())
        values = {
            "client_name": row["client_name"],
            "client_first_name": row["contact_name"].split()[0],
            "invoice_no": row["id"],
            "amount_due": view["outstanding"],
            "invoice_amount": view["amount"],
            "issue_date": format_date(date.fromisoformat(row["issue_date"])),
            "due_date": format_date(date.fromisoformat(row["due_date"])),
            "days_overdue": str(max(view["days_overdue"], 0)),
            "sender_name": self.config.sender_name,
            "payment_details": self.config.payment_details,
        }
        subject = render.fill(subject_template, values).strip()
        body = render.fill(body_template, values).strip()
        if len(subject) > self.config.max_subject_chars:
            problems.append(f"subject: longer than {self.config.max_subject_chars} characters")
        if len(body) > self.config.max_body_chars:
            problems.append(f"body: longer than {self.config.max_body_chars} characters")
        if problems:
            raise LedgerError("RENDER_REJECTED", "Template rejected; fix and retry",
                              problems=problems)
        return {"subject": subject, "body": body, "amount_due_paise": view["outstanding_paise"]}

    def render_reminder(self, invoice_id: str, tone_level: int, language: str,
                        subject_template: str, body_template: str) -> dict:
        """Preview a reminder without saving it."""
        r = self._render(invoice_id, tone_level, language, subject_template, body_template)
        return {"ok": True, "subject": r["subject"], "body": r["body"]}

    def queue_reminder(self, invoice_id: str, tone_level: int, language: str,
                       subject_template: str, body_template: str, run_id: str | None = None) -> dict:
        """Policy-check, render and queue a reminder for the owner's approval.

        Policy is re-checked here even if the caller already checked it.
        """
        self._validate_tone_language(tone_level, language)
        policy = self.check_policy(invoice_id, tone_level)
        if not policy["allowed"]:
            with self._tx():
                cur = self.conn.execute(
                    "INSERT INTO reminders (invoice_id, tone_level, language, amount_due_paise, "
                    "status, reasons, run_id, created_at) VALUES (?, ?, ?, 0, 'DROPPED', ?, ?, ?)",
                    (invoice_id, tone_level, language, json.dumps(policy["reasons"]), run_id, _now()))
                self._audit("drop_reminder", "reminder", cur.lastrowid,
                            {"reasons": policy["reasons"]}, run_id)
            return {"ok": False, "error_code": "POLICY_BLOCKED", "reasons": policy["reasons"],
                    "message": "Reminder not queued: " + ", ".join(policy["reasons"])}

        r = self._render(invoice_id, tone_level, language, subject_template, body_template)
        with self._tx():
            cur = self.conn.execute(
                "INSERT INTO reminders (invoice_id, tone_level, language, subject, body, "
                "amount_due_paise, status, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?)",
                (invoice_id, tone_level, language, r["subject"], r["body"],
                 r["amount_due_paise"], run_id, _now()))
            self._audit("queue_reminder", "reminder", cur.lastrowid,
                        {"invoice_id": invoice_id, "tone_level": tone_level, "language": language},
                        run_id)
        return {"ok": True, "reminder_id": cur.lastrowid, "status": "QUEUED",
                "subject": r["subject"], "body": r["body"]}

    def list_reminders(self, status: str = "QUEUED") -> dict:
        rows = self.conn.execute(
            "SELECT r.*, i.client_id, c.name AS client_name, c.email FROM reminders r "
            "JOIN invoices i ON i.id = r.invoice_id JOIN clients c ON c.id = i.client_id "
            "WHERE r.status = ? ORDER BY r.id", (status,)).fetchall()
        return {"ok": True, "reminders": [
            {"reminder_id": r["id"], "invoice_id": r["invoice_id"], "client_name": r["client_name"],
             "email": r["email"], "tone_level": r["tone_level"], "language": r["language"],
             "subject": r["subject"], "body": r["body"], "status": r["status"],
             "reasons": json.loads(r["reasons"]), "sent_on": r["sent_on"]} for r in rows]}

    def _reminder(self, reminder_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if row is None:
            raise LedgerError("UNKNOWN_REMINDER", f"No reminder {reminder_id!r}")
        return row

    @owner_only
    def approve_reminder(self, reminder_id: int, subject: str | None = None,
                         body: str | None = None) -> dict:
        rem = self._reminder(reminder_id)
        states.check_reminder_transition(rem["status"], "APPROVED")
        view = self._invoice_view(self._invoice_row(rem["invoice_id"]), self.config.today())
        if view["outstanding_paise"] != rem["amount_due_paise"]:
            raise LedgerError("STALE_REMINDER", "Amount due changed since drafting; redraft it")
        edited = (subject is not None and subject != rem["subject"]) or \
                 (body is not None and body != rem["body"])
        if edited and not ((subject or rem["subject"]).strip() and (body or rem["body"]).strip()):
            raise LedgerError("INVALID_REQUEST", "Subject and body cannot be empty")
        with self._tx():
            self.conn.execute(
                "UPDATE reminders SET status = 'APPROVED', subject = ?, body = ?, "
                "edited_by_owner = ? WHERE id = ?",
                (subject if subject is not None else rem["subject"],
                 body if body is not None else rem["body"], int(edited), reminder_id))
            self._audit("approve_reminder", "reminder", reminder_id, {"edited": edited})
        return {"ok": True, "reminder_id": reminder_id, "status": "APPROVED", "edited": edited}

    @owner_only
    def skip_reminder(self, reminder_id: int) -> dict:
        rem = self._reminder(reminder_id)
        states.check_reminder_transition(rem["status"], "SKIPPED")
        with self._tx():
            self.conn.execute("UPDATE reminders SET status = 'SKIPPED' WHERE id = ?", (reminder_id,))
            self._audit("skip_reminder", "reminder", reminder_id)
        return {"ok": True, "reminder_id": reminder_id, "status": "SKIPPED"}

    @owner_only
    def mark_sent(self, reminder_id: int, sent_on: str | None = None) -> dict:
        rem = self._reminder(reminder_id)
        states.check_reminder_transition(rem["status"], "SENT")
        on = self._as_of(sent_on).isoformat()
        with self._tx():
            self.conn.execute("UPDATE reminders SET status = 'SENT', sent_on = ? WHERE id = ?",
                              (on, reminder_id))
            self._audit("mark_sent", "reminder", reminder_id, {"sent_on": on})
        return {"ok": True, "reminder_id": reminder_id, "status": "SENT", "sent_on": on}

    # ---------------------------------------------------------------- holds

    @owner_only
    def set_invoice_hold(self, invoice_id: str, hold: str | None, reason: str) -> dict:
        row = self._invoice_row(invoice_id)
        status = self._invoice_view(row, self.config.today())["status"]
        states.check_hold_transition(row["hold"], hold, status)
        with self._tx():
            self.conn.execute("UPDATE invoices SET hold = ? WHERE id = ?", (hold, invoice_id))
            if hold:
                self._cancel_pending_reminders(invoice_id, f"invoice_{hold.lower()}", None)
            self._audit("set_hold", "invoice", invoice_id,
                        {"from": row["hold"], "to": hold, "reason": reason})
        return {"ok": True, "invoice_id": invoice_id, "hold": hold}

    # ------------------------------------------------------------- reporting

    def get_audit_log(self, entity_id: str | None = None, run_id: str | None = None,
                      limit: int = 50) -> dict:
        sql, params = "SELECT * FROM audit WHERE 1=1", []
        if entity_id:
            sql += " AND entity_id = ?"
            params.append(str(entity_id))
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)
        rows = self.conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*params, int(limit)))
        return {"ok": True, "events": [{**dict(r), "details": json.loads(r["details"])} for r in rows]}

    def run_report(self, run_id: str) -> dict:
        counts = dict(self.conn.execute(
            "SELECT action, COUNT(*) FROM audit WHERE run_id = ? GROUP BY action", (run_id,)).fetchall())
        auto = self.conn.execute(
            "SELECT COUNT(*) FROM match_proposals WHERE run_id = ? AND decision = 'AUTO_APPLIED'",
            (run_id,)).fetchone()[0]
        return {"ok": True, "run_id": run_id,
                "payments_auto_matched": auto,
                "matches_needing_confirmation": counts.get("propose_match", 0) - auto,
                "reminders_queued": counts.get("queue_reminder", 0),
                "reminders_dropped_by_policy": counts.get("drop_reminder", 0),
                "pending_match_confirmations_total": len(self.list_pending_matches()["proposals"]),
                "reminders_awaiting_approval_total": len(self.list_reminders("QUEUED")["reminders"])}

    def check_invariants(self) -> dict:
        violations = invariants.check(self.conn, self.config)
        return {"ok": not violations, "violations": violations}

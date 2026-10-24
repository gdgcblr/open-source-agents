import json
import time
import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ReadMail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    since: date
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10000)


class ReadCalendar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=14, ge=1, le=90)


class FindContacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=100)


class MailChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=500)
    value: bool


class ContactChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default="", max_length=500)
    given_name: str = Field(min_length=1, max_length=100)
    family_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=254)


READS = {"mail.read": ReadMail, "calendar.read": ReadCalendar, "contacts.search": FindContacts}
WRITES = {"mail.flag": MailChange, "mail.mark_read": MailChange, "contacts.save": ContactChange}


def validate(operation, payload):
    schema = (READS | WRITES).get(operation)
    if schema is None:
        raise ValueError("Operation is not permitted.")
    return schema.model_validate(payload).model_dump(mode="json")


def host_approval(operation, payload, expires):
    """Only the Mac host terminal can approve. No model or HTTP approval input exists."""
    if time.time() >= expires:
        raise ValueError("Approval request expired.")
    challenge = uuid.uuid4().hex[:8]
    with open("/dev/tty", "r+") as tty:
        tty.write(
            f"\nChange: {operation}\n{json.dumps(payload, ensure_ascii=True, indent=2)}\n"
            f"Type {challenge} to apply this exact change: "
        )
        tty.flush()
        approved = tty.readline().strip() == challenge
    if not approved or time.time() >= expires:
        raise ValueError("Change denied or approval expired.")


def propose(store, operation, payload):
    if operation not in WRITES:
        raise ValueError("Unknown change.")
    payload = validate(operation, payload)
    key = uuid.uuid4().hex
    with store.connect() as db:
        pending = db.execute(
            "SELECT count(*) FROM action_requests WHERE state='pending' AND expires>?",
            (time.time(),),
        ).fetchone()[0]
        if pending >= 20:
            raise ValueError("Too many pending changes. Review existing requests first.")
        db.execute(
            "INSERT INTO action_requests VALUES(?,?,?,?,?,NULL)",
            (key, operation, json.dumps(payload, sort_keys=True), time.time() + 300, "pending"),
        )
    store.audit("action_proposed", key)
    return {
        "request_id": key,
        "operation": operation,
        "preview": payload,
        "expires_in_seconds": 300,
        "next": f"Run migine apply {key}; approve on the Mac.",
    }


def apply_request(store, adapter, key):
    with store.connect() as db:
        row = db.execute("SELECT * FROM action_requests WHERE id=?", (key,)).fetchone()
        if not row or row["state"] != "pending" or row["expires"] <= time.time():
            raise ValueError("Unknown, used, or expired change request.")
        changed = db.execute(
            "UPDATE action_requests SET state='executing' WHERE id=? AND state='pending'", (key,)
        )
        if changed.rowcount != 1:
            raise ValueError("Request is already in use.")
    try:
        result = adapter.call(row["operation"], json.loads(row["payload"]), row["expires"])
    except Exception:
        with store.connect() as db:
            db.execute("UPDATE action_requests SET state='failed_or_uncertain' WHERE id=?", (key,))
        store.audit("action_failed_or_uncertain", key)
        raise
    with store.connect() as db:
        db.execute(
            "UPDATE action_requests SET state='completed',result=? WHERE id=?",
            (json.dumps(result), key),
        )
    store.audit("action_completed", key)
    return result

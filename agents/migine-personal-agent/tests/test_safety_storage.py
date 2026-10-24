import time

import pytest

from migine.config import local_url
from migine.demo import load_demo
from migine.models import FinancialRecord
from migine.safety import apply_request, host_approval, propose, validate
from migine.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_evidence_must_exist(store):
    store.add_source(
        {
            "id": "1",
            "title": "x",
            "body": "Nothing financial here.",
            "received": "2026-10-01",
            "url": "demo:1",
        }
    )
    record = FinancialRecord(
        kind="charge",
        provider="x",
        amount="10.00",
        currency="INR",
        occurred_on="2026-10-01",
        status="credited",
        evidence="Invented charge evidence",
    )
    with pytest.raises(ValueError):
        store.add_record("1", record)


def test_pending_records_not_in_summary(store):
    load_demo(store, "2026-10")
    with store.connect() as db:
        db.execute("UPDATE records SET review='pending'")
    assert store.records() == []
    candidate = store.records("pending")[0]
    store.review(candidate["id"], True)
    assert len(store.records()) == 1


def test_source_change_invalidates_records_and_vectors(store):
    load_demo(store, "2026-10")
    source = {
        "id": "demo-2026-10-0",
        "title": "updated",
        "body": "New content",
        "received": "2026-10-01",
        "url": "demo:0",
    }
    with store.connect() as db:
        db.execute("INSERT INTO vectors VALUES(?,?,?)", (source["id"], "test", "[1]"))
    store.add_source(source)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM vectors").fetchone()[0] == 0
    assert len(store.records()) == 3


def test_source_deletion_cascades(store):
    load_demo(store, "2026-10")
    store.forget_source("demo-2026-10-0")
    assert len(store.records()) == 3


def test_preferences_persist(store):
    store.remember("bill_notice_days", "3")
    reopened = Store(store.path.parent)
    with reopened.connect() as db:
        assert db.execute("SELECT value FROM preferences").fetchone()[0] == "3"


def test_accepted_record_can_be_revoked(store):
    load_demo(store, "2026-10")
    key = store.records()[0]["id"]
    store.review(key, False)
    assert len(store.records()) == 3


@pytest.mark.parametrize("value", ["-1", "91", "tomorrow"])
def test_notice_days_validation(store, value):
    with pytest.raises(ValueError):
        store.remember("bill_notice_days", value)


@pytest.mark.parametrize(
    "op,payload",
    [
        ("shell", {"command": "rm"}),
        ("mail.send", {}),
        ("calendar.read", {"days": 999}),
        ("contacts.search", {"query": ""}),
        ("mail.flag", {"id": "1", "value": True, "approved": True}),
    ],
)
def test_reject_unsupported_or_extra_arguments(op, payload):
    with pytest.raises(ValueError):
        validate(op, payload)


def test_proposal_is_not_execution(store):
    result = propose(store, "mail.flag", {"id": "1", "value": True})
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT state FROM action_requests WHERE id=?", (result["request_id"],)
            ).fetchone()[0]
            == "pending"
        )


def test_expiry_prevents_adapter_call(store):
    request = propose(store, "mail.flag", {"id": "1", "value": True})
    with store.connect() as db:
        db.execute("UPDATE action_requests SET expires=?", (time.time() - 1,))
    with pytest.raises(ValueError):
        apply_request(store, None, request["request_id"])


def test_failed_action_cannot_be_replayed(store):
    class Denied:
        def call(self, *_args):
            raise ValueError("denied")

    request = propose(store, "mail.flag", {"id": "1", "value": True})
    with pytest.raises(ValueError):
        apply_request(store, Denied(), request["request_id"])
    with pytest.raises(ValueError):
        apply_request(store, None, request["request_id"])


def test_completed_action_cannot_be_replayed(store):
    class Fake:
        def call(self, operation, payload, expires):
            return {"changed": True}

    request = propose(store, "mail.flag", {"id": "1", "value": True})
    apply_request(store, Fake(), request["request_id"])
    with pytest.raises(ValueError):
        apply_request(store, None, request["request_id"])


def test_headless_host_cannot_approve(monkeypatch):
    def no_tty(*_args):
        raise OSError("no tty")

    monkeypatch.setattr("builtins.open", no_tty)
    with pytest.raises(OSError):
        host_approval("mail.flag", {"id": "1", "value": True}, time.time() + 20)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com",
        "http://127.0.0.1@evil.com",
        "http://localhost/path",
    ],
)
def test_cloud_endpoints_rejected(url):
    with pytest.raises(ValueError):
        local_url(url)

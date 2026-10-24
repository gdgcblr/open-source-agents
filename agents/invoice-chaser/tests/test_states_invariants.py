import itertools

import pytest

from ledger import LedgerError, states
from tests.conftest import GOOD_BODY, GOOD_SUBJECT, payment_id

HOLDS = [None, "DISPUTED", "WRITTEN_OFF"]
LEGAL_HOLDS = {(None, "DISPUTED"), (None, "WRITTEN_OFF"), ("DISPUTED", None),
               ("DISPUTED", "WRITTEN_OFF")}


@pytest.mark.parametrize("current,new", list(itertools.product(HOLDS, HOLDS)))
def test_hold_transitions_exhaustive(current, new):
    if (current, new) in LEGAL_HOLDS:
        states.check_hold_transition(current, new, "OVERDUE")
    else:
        with pytest.raises(LedgerError):
            states.check_hold_transition(current, new, "OVERDUE")


REMINDER_STATES = list(states.REMINDER_TRANSITIONS)
LEGAL_REMINDER = {("QUEUED", "APPROVED"), ("QUEUED", "SKIPPED"), ("QUEUED", "CANCELLED"),
                  ("APPROVED", "SENT"), ("APPROVED", "CANCELLED"), ("SENT", "RESPONDED")}


@pytest.mark.parametrize("current,new", list(itertools.product(REMINDER_STATES, REMINDER_STATES)))
def test_reminder_transitions_exhaustive(current, new):
    if (current, new) in LEGAL_REMINDER:
        states.check_reminder_transition(current, new)
    else:
        with pytest.raises(LedgerError):
            states.check_reminder_transition(current, new)


def test_paid_invoice_cannot_be_held(agent, owner):
    agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-001"], 0.97, "TDS")
    with pytest.raises(LedgerError) as e:
        owner.set_invoice_hold("INV-2026-001", "DISPUTED", "x")
    assert e.value.code == "ILLEGAL_TRANSITION"


def test_agent_cannot_hold(agent):
    with pytest.raises(LedgerError) as e:
        agent.set_invoice_hold("INV-2026-004", "DISPUTED", "client said so")
    assert e.value.code == "FORBIDDEN"


def test_actor_must_be_known(db_path, config):
    from ledger import Ledger
    with pytest.raises(ValueError):
        Ledger(db_path, config, actor="admin")


def test_sample_flow_keeps_invariants(agent, owner):
    agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-001"], 0.97, "TDS")
    agent.propose_match(payment_id(agent, "GREEN LEAF"), ["INV-2026-012"], 0.95, "TDS")
    for item in agent.get_chase_list()["items"]:
        if item["can_queue_reminder"]:
            agent.queue_reminder(item["invoice_id"], item["recommended_tone"], item["language"],
                                 GOOD_SUBJECT, GOOD_BODY)
    assert owner.check_invariants() == {"ok": True, "violations": []}


def test_invariant_violation_rolls_back(owner):
    """Simulate a bug that over-allocates: the transaction must not commit."""
    pid = payment_id(owner, "ACME")
    with pytest.raises(LedgerError) as e:
        with owner._tx():
            owner.conn.execute(
                "INSERT INTO allocations (payment_id, invoice_id, paid_paise, tds_paise, applied_by, "
                "created_at) VALUES (?, 'INV-2026-001', 9000000, 0, 'test', 'now')", (pid,))
    assert e.value.code == "INVARIANT_VIOLATION"
    assert any(v.startswith("I1") for v in e.value.details["violations"])
    assert owner.conn.execute("SELECT COUNT(*) FROM allocations").fetchone()[0] == 0


def test_invariants_detect_unaudited_reminder(owner):
    owner.conn.execute("INSERT INTO reminders (invoice_id, tone_level, language, amount_due_paise, "
                       "status, created_at) VALUES ('INV-2026-004', 1, 'en', 1800000, 'QUEUED', 'now')")
    assert any(v.startswith("I8") for v in owner.check_invariants()["violations"])


def test_invariants_detect_stale_pending_reminder(agent, owner):
    queue = agent.queue_reminder("INV-2026-004", 2, "en", GOOD_SUBJECT, GOOD_BODY)
    owner.conn.execute("UPDATE reminders SET amount_due_paise = 1 WHERE id = ?", (queue["reminder_id"],))
    assert any(v.startswith("I7") for v in owner.check_invariants()["violations"])


def test_every_write_is_audited_with_run_id(agent):
    agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-001"], 0.97, "TDS", run_id="run-42")
    agent.queue_reminder("INV-2026-004", 2, "en", GOOD_SUBJECT, GOOD_BODY, run_id="run-42")
    actions = [e["action"] for e in agent.get_audit_log(run_id="run-42")["events"]]
    assert sorted(actions) == ["apply_allocation", "propose_match", "queue_reminder"]
    assert {e["actor"] for e in agent.get_audit_log(run_id="run-42")["events"]} == {"agent"}
    report = agent.run_report("run-42")
    assert (report["payments_auto_matched"], report["reminders_queued"]) == (1, 1)

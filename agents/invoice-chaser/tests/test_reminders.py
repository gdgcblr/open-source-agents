import pytest

from ledger import LedgerError
from tests.conftest import GOOD_BODY, GOOD_SUBJECT, payment_id


def queue(ledger, invoice="INV-2026-004", tone=2, run_id=None):
    return ledger.queue_reminder(invoice, tone, "en", GOOD_SUBJECT, GOOD_BODY, run_id=run_id)


def test_full_lifecycle(agent, owner):
    r = queue(agent)
    assert r["status"] == "QUEUED"
    assert owner.approve_reminder(r["reminder_id"])["edited"] is False
    sent = owner.mark_sent(r["reminder_id"])
    assert (sent["status"], sent["sent_on"]) == ("SENT", "2026-10-24")


def test_owner_edit_is_recorded(agent, owner):
    rid = queue(agent)["reminder_id"]
    owner.approve_reminder(rid, body="Hi Rohit, quick nudge on INV-2026-004 (₹18,000). Thanks!")
    rem = owner.list_reminders("APPROVED")["reminders"][0]
    assert rem["body"].startswith("Hi Rohit, quick nudge")
    assert owner.get_audit_log(entity_id=str(rid))["events"][0]["details"] == {"edited": True}


def test_only_one_pending_reminder_per_invoice(agent):
    queue(agent)
    r = queue(agent)
    assert (r["ok"], r["reasons"]) == (False, ["PENDING_REMINDER_EXISTS"])


def test_cooldown_after_sending(agent, owner):
    rid = queue(agent)["reminder_id"]
    owner.approve_reminder(rid)
    owner.mark_sent(rid)
    assert "COOLDOWN" in queue(agent)["reasons"]
    assert agent.check_policy("INV-2026-004", 2, "2026-10-29")["allowed"]  # 5 days later


def test_policy_block_is_recorded_as_dropped(agent):
    r = queue(agent, invoice="INV-2026-002", tone=2, run_id="run-1")
    assert r["error_code"] == "POLICY_BLOCKED"
    assert agent.list_reminders("DROPPED")["reminders"][0]["reasons"] == ["TONE_ABOVE_CLIENT_CAP"]
    assert agent.run_report("run-1")["reminders_dropped_by_policy"] == 1


def test_payment_cancels_pending_reminder(agent):
    rid = queue(agent, invoice="INV-2026-012")["reminder_id"]
    agent.propose_match(payment_id(agent, "GREEN LEAF"), ["INV-2026-012"], 0.95, "TDS")
    assert [r["reminder_id"] for r in agent.list_reminders("CANCELLED")["reminders"]] == [rid]


def test_partial_payment_cancels_stale_reminder(agent, owner):
    rid = queue(agent, invoice="INV-2026-006")["reminder_id"]
    owner.confirm_match(agent.propose_match(payment_id(agent, "SHARMA"), ["INV-2026-006"], 0.9,
                                            "partial")["proposal_id"])
    assert agent.list_reminders("CANCELLED")["reminders"][0]["reminder_id"] == rid
    assert queue(agent, invoice="INV-2026-006")["ok"]  # redraft at the new amount


def test_dispute_cancels_pending_reminder(agent, owner):
    queue(agent)
    owner.set_invoice_hold("INV-2026-004", "DISPUTED", "menu not final")
    assert len(owner.list_reminders("CANCELLED")["reminders"]) == 1


@pytest.mark.parametrize("method", ["approve_reminder", "skip_reminder", "mark_sent"])
def test_agent_cannot_act_on_queue(agent, method):
    rid = queue(agent)["reminder_id"]
    with pytest.raises(LedgerError) as e:
        getattr(agent, method)(rid)
    assert e.value.code == "FORBIDDEN"


def test_illegal_reminder_transitions(agent, owner):
    rid = queue(agent)["reminder_id"]
    with pytest.raises(LedgerError) as e:
        owner.mark_sent(rid)  # must be approved first
    assert e.value.code == "ILLEGAL_TRANSITION"
    owner.skip_reminder(rid)
    with pytest.raises(LedgerError):
        owner.approve_reminder(rid)


@pytest.mark.parametrize("tone,language", [(4, "en"), (-1, "en"), (True, "en"), (1, "fr")])
def test_invalid_tone_or_language(agent, tone, language):
    with pytest.raises(LedgerError) as e:
        agent.queue_reminder("INV-2026-004", tone, language, GOOD_SUBJECT, GOOD_BODY)
    assert e.value.code == "INVALID_REQUEST"


def test_render_rejection_writes_nothing(agent):
    with pytest.raises(LedgerError):
        agent.queue_reminder("INV-2026-004", 1, "en", GOOD_SUBJECT, "Pay 18000 for {invoice_no} {amount_due}")
    assert agent.list_reminders("QUEUED")["reminders"] == []
    assert agent.check_invariants()["ok"]

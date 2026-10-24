import pytest

from ledger import ageing


@pytest.mark.parametrize("days,expected", [(-5, "not_overdue"), (0, "not_overdue"), (1, "1-15"),
                                           (15, "1-15"), (16, "16-30"), (45, "31-60"), (61, "60+")])
def test_bucket(days, expected):
    assert ageing.bucket(days) == expected


@pytest.mark.parametrize("days,flags,last,expected", [
    (-2, set(), None, 0), (3, set(), None, 1), (20, set(), None, 2),
    (40, set(), None, 2),                          # final notice needs opt-in
    (40, {"allow_final_notice"}, None, 3),
    (40, {"gentle"}, None, 1),                     # gentle caps at 1
    (3, set(), 2, 2),                              # never de-escalate
])
def test_recommended_tone(days, flags, last, expected):
    assert ageing.recommended_tone(days, flags, last) == expected


def test_priority_orders_overdue_above_not_due():
    assert ageing.priority(100, 1) > ageing.priority(100_000_000, -1)
    assert ageing.priority(100, 1) > ageing.priority(100_000_000, 0)  # due today
    assert ageing.priority(1, -1) > ageing.priority(1, -3)            # sooner due first
    assert ageing.priority(5_000_000, 30) > ageing.priority(5_000_000, 10)


def test_chase_list_on_sample(owner):
    items = {i["invoice_id"]: i for i in owner.get_chase_list()["items"]}
    assert "INV-2026-009" not in items  # due in 22 days
    assert "INV-2026-011" not in items  # due in 6 days
    assert items["INV-2026-008"]["recommended_tone"] == 0
    assert items["INV-2026-002"]["recommended_tone"] == 1      # gentle client
    assert items["INV-2026-005"]["recommended_tone"] == 3      # opted-in client
    ranked = [i["invoice_id"] for i in owner.get_chase_list()["items"]]
    assert ranked[0] == "INV-2026-005" and ranked[-1] == "INV-2026-008"


def test_paid_invoice_leaves_chase_list(agent):
    from tests.conftest import payment_id
    agent.propose_match(payment_id(agent, "GREEN LEAF"), ["INV-2026-012"], 0.95, "TDS")
    assert "INV-2026-012" not in [i["invoice_id"] for i in agent.get_chase_list()["items"]]


@pytest.mark.parametrize("invoice,tone,reason", [
    ("INV-2026-009", 0, "NOT_DUE_YET"),
    ("INV-2026-002", 2, "TONE_ABOVE_CLIENT_CAP"),
    ("INV-2026-007", 3, "TONE_ABOVE_CLIENT_CAP"),
])
def test_policy_reasons(owner, invoice, tone, reason):
    assert reason in owner.check_policy(invoice, tone)["reasons"]


def test_policy_too_old(owner):
    assert "TOO_OLD_CONSIDER_WRITE_OFF" in owner.check_policy("INV-2026-002", 1, "2027-06-01")["reasons"]


def test_policy_blocks_held_invoice(owner):
    owner.set_invoice_hold("INV-2026-004", "DISPUTED", "client says menu not final")
    assert owner.check_policy("INV-2026-004", 1)["reasons"] == ["INVOICE_DISPUTED"]

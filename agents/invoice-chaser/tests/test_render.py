import pytest

from ledger import LedgerError
from ledger.render import template_problems
from tests.conftest import GOOD_BODY, GOOD_SUBJECT


def test_good_template_renders_ledger_values(owner):
    r = owner.render_reminder("INV-2026-004", 2, "en", GOOD_SUBJECT, GOOD_BODY)
    assert r["subject"] == "Invoice INV-2026-004"
    assert "Hi Rohit" in r["body"] and "₹18,000" in r["body"] and "5 Oct 2026" in r["body"]


def test_rendered_amount_reflects_partial_payment(agent, owner):
    from tests.conftest import payment_id
    owner.confirm_match(agent.propose_match(payment_id(agent, "SHARMA"), ["INV-2026-006"], 0.9,
                                            "partial")["proposal_id"])
    assert "₹12,000" in owner.render_reminder("INV-2026-006", 2, "en", GOOD_SUBJECT, GOOD_BODY)["body"]


@pytest.mark.parametrize("text,fragment", [
    ("Invoice for 50000 is due", "digits"),
    ("Pay ₹ soon", "currency"),
    ("Pay Rs. soon", "currency"),
    ("Pay INR soon", "currency"),
    ("fifty thousand rupees pending", "number word"),
    ("pachas hazaar pending hai", "number word"),
    ("Due on 6 Oct", "digits"),
    ("Hello {client_nme}", "unknown slot"),
    ("Hello {client_name", "unbalanced"),
    ("We will take legal action", "legal action"),
    ("Or we go to court", "court"),
])
def test_guard_rejects(text, fragment):
    problems = template_problems(text, 1, "body")
    assert any(fragment in p for p in problems), problems


def test_guard_word_boundaries_avoid_false_positives():
    assert template_problems("Any issue with the invoice? Courteous follow-up.", 1, "body") == []


def test_final_notice_wording_only_at_tone_3():
    text = "This is a final notice for {invoice_no}"
    assert template_problems(text, 2, "body")
    assert template_problems(text, 3, "body") == []


@pytest.mark.parametrize("subject,body,fragment", [
    ("", GOOD_BODY, "subject: empty"),
    (GOOD_SUBJECT, "Hi {client_first_name}, please pay {amount_due}", "must include {invoice_no}"),
    (GOOD_SUBJECT, "Invoice {invoice_no} is pending", "must include {amount_due}"),
    ("x" * 200, GOOD_BODY, "longer than"),
    (GOOD_SUBJECT, GOOD_BODY + " ok" * 600, "longer than"),
])
def test_render_rejections(owner, subject, body, fragment):
    with pytest.raises(LedgerError) as e:
        owner.render_reminder("INV-2026-004", 1, "en", subject, body)
    assert e.value.code == "RENDER_REJECTED"
    assert any(fragment in p for p in e.value.details["problems"])


def test_hinglish_template(owner):
    body = ("Namaste {client_first_name} ji, invoice {invoice_no} ka {amount_due} payment "
            "{due_date} ko due tha. Jab time mile please check kar lijiye. - {sender_name}")
    assert "₹18,000" in owner.render_reminder("INV-2026-004", 1, "hinglish", GOOD_SUBJECT, body)["body"]

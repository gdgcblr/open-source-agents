from pathlib import Path

from rentrakshak.services.listing_parser import extract_property, find_contradictions
from rentrakshak.services.risk_rules import classify_risk, detect_red_flags
from rentrakshak.models.schemas import RiskCategory, Severity

FIX = Path(__file__).parent / "fixtures"


def test_urgent_payment_and_otp():
    text = (FIX / "suspicious_listing.txt").read_text()
    prop = extract_property(text)
    findings = detect_red_flags(text, None, find_contradictions(text, None, prop))
    ids = {f.rule_id for f in findings}
    assert "RF-001" in ids or "RF-002" in ids
    assert "RF-005" in ids
    cat, _ = classify_risk(findings, prop)
    assert cat == RiskCategory.CRITICAL


def test_clean_listing_no_critical():
    text = (FIX / "clean_listing.txt").read_text()
    prop = extract_property(text)
    findings = detect_red_flags(text, None, [])
    assert not any(f.severity == Severity.CRITICAL for f in findings)


def test_evidence_excerpt_from_input():
    text = "Please send OTP for booking"
    findings = detect_red_flags(text, None, [])
    assert any("OTP" in f.evidence_excerpt for f in findings)


def test_contradiction_rule():
    listing = "Owner direct 2 BHK Whitefield rent 25000"
    chat = "I am broker, rent is 40000"
    prop = extract_property(listing, monthly_rent_inr=25000)
    issues = find_contradictions(listing, chat, prop)
    findings = detect_red_flags(listing, chat, issues)
    assert any(f.rule_id.startswith("RF-C") for f in findings)

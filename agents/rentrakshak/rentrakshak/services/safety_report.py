from __future__ import annotations

from rentrakshak.guardrails.content_safety import sanitize_untrusted_content, strip_instruction_override
from rentrakshak.guardrails.model_armor import screen_text
from rentrakshak.models.schemas import SafetyReport
from rentrakshak.services.checklist import build_rental_checklist, get_karnataka_rental_guidance
from rentrakshak.services.community import summarize_community_for_locality
from rentrakshak.services.deposit import assess_deposit_terms
from rentrakshak.services.listing_parser import extract_property, find_contradictions
from rentrakshak.services.rent_estimator import estimate_bengaluru_rent
from rentrakshak.services.risk_rules import (
    classify_risk,
    detect_red_flags,
    questions_to_ask,
    verification_actions,
)


def generate_rental_safety_report(
    listing_text: str,
    chat_text: str | None = None,
    *,
    locality_hint: str | None = None,
    monthly_rent_inr: int | None = None,
    deposit_inr: int | None = None,
    bhk: str | None = None,
    furnishing: str | None = None,
    maintenance_inr: int | None = None,
    property_type: str | None = None,
    db_path=None,
) -> SafetyReport:
    safe_listing, guard_notes = sanitize_untrusted_content(listing_text)
    safe_chat = strip_instruction_override(chat_text or "") if chat_text else None
    guard_notes = list(guard_notes)

    armor_in = screen_text(safe_listing, direction="input")
    if armor_in.service_available and armor_in.blocked:
        guard_notes.append("Model Armor blocked input; review manually.")

    prop = extract_property(
        safe_listing,
        locality_hint=locality_hint,
        monthly_rent_inr=monthly_rent_inr,
        deposit_inr=deposit_inr,
        bhk=bhk,
        furnishing=furnishing,
        maintenance_inr=maintenance_inr,
        property_type=property_type,
    )
    contradictions = find_contradictions(safe_listing, safe_chat, prop)
    findings = detect_red_flags(safe_listing, safe_chat, contradictions)
    risk_cat, risk_reason = classify_risk(findings, prop)

    rent_est = None
    if prop.locality:
        rent_est = estimate_bengaluru_rent(
            prop.locality,
            bhk=prop.bhk,
            furnishing=prop.furnishing,
            property_type=prop.property_type,
        )

    deposit = assess_deposit_terms(prop, safe_listing)
    checklist = build_rental_checklist()
    legal = get_karnataka_rental_guidance()

    community = None
    if prop.locality:
        community = summarize_community_for_locality(prop.locality, db_path=db_path)

    limitations = [
        "This report is based only on text you supplied; the property and owner are not independently verified.",
        "Community posts are anonymous and unverified.",
    ]
    if rent_est and not rent_est.sufficient_data:
        limitations.append("Rent estimate unavailable — do not infer market rent from the model.")

    return SafetyReport(
        property=prop,
        missing_or_contradictory=contradictions + prop.raw_notes,
        risk_category=risk_cat,
        risk_reasoning=risk_reason,
        findings=findings,
        verification_actions=verification_actions(findings, prop),
        rent_estimate=rent_est,
        deposit_assessment=deposit,
        checklist_highlights=[c.title for c in checklist[:5]],
        questions_to_ask=questions_to_ask(findings),
        legal_sources=legal,
        community_summary=community,
        limitations=limitations,
        guardrail_notes=guard_notes,
    )

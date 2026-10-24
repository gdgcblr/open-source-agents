from __future__ import annotations

from pathlib import Path
from typing import Any

from rentrakshak.models.schemas import AnonymousExperienceInput, VacatingPostInput
from rentrakshak.services.checklist import build_rental_checklist, get_karnataka_rental_guidance
from rentrakshak.services.community import (
    create_anonymous_experience,
    report_community_content,
    search_anonymous_experiences,
)
from rentrakshak.services.deposit import assess_deposit_terms
from rentrakshak.services.listing_parser import extract_property, find_contradictions
from rentrakshak.services.rent_estimator import estimate_bengaluru_rent
from rentrakshak.services.risk_rules import (
    classify_risk,
    detect_red_flags,
    verification_actions,
)
from rentrakshak.services.safety_report import generate_rental_safety_report
from rentrakshak.services.vacating import (
    create_vacating_post,
    search_available_rooms,
    update_vacating_post_status,
)


def analyze_rental_listing(
    listing_text: str,
    chat_text: str = "",
    locality: str = "",
    monthly_rent_inr: int = 0,
    deposit_inr: int = 0,
    bhk: str = "",
    furnishing: str = "",
) -> dict[str, Any]:
    """Extract structured property details and contradictions from listing and optional chat."""
    prop = extract_property(
        listing_text,
        locality_hint=locality or None,
        monthly_rent_inr=monthly_rent_inr or None,
        deposit_inr=deposit_inr or None,
        bhk=bhk or None,
        furnishing=furnishing or None,
    )
    contradictions = find_contradictions(listing_text, chat_text or None, prop)
    return {
        "status": "complete",
        "agent_note": "Listing parsed — summarize for the user; do not call analyze_rental_listing again.",
        "property": prop.model_dump(),
        "contradictions": contradictions,
    }


def detect_rental_red_flags(listing_text: str, chat_text: str = "") -> dict[str, Any]:
    """Run deterministic red-flag rules with evidence excerpts."""
    prop = extract_property(listing_text)
    contradictions = find_contradictions(listing_text, chat_text or None, prop)
    findings = detect_red_flags(listing_text, chat_text or None, contradictions)
    risk_cat, reason = classify_risk(findings, prop)
    return {
        "findings": [f.model_dump() for f in findings],
        "risk_category": risk_cat.value,
        "risk_reasoning": reason,
        "verification_actions": verification_actions(findings, prop),
    }


def estimate_bengaluru_rent_tool(
    locality: str,
    bhk: str = "",
    furnishing: str = "",
    property_type: str = "",
) -> dict[str, Any]:
    """Transparent rent range from local comparables dataset."""
    result = estimate_bengaluru_rent(
        locality,
        bhk=bhk or None,
        furnishing=furnishing or None,
        property_type=property_type or None,
    )
    return result.model_dump()


def assess_deposit_terms_tool(
    monthly_rent_inr: int,
    deposit_inr: int,
    listing_text: str = "",
) -> dict[str, Any]:
    prop = extract_property(
        listing_text or "",
        monthly_rent_inr=monthly_rent_inr,
        deposit_inr=deposit_inr,
    )
    return assess_deposit_terms(prop, listing_text)


def build_rental_checklist_tool() -> dict[str, Any]:
    items = build_rental_checklist()
    return {
        "status": "complete",
        "agent_note": "Checklist delivered — summarize for the user; do not call this tool again this turn.",
        "items": [i.model_dump() for i in items],
    }


def get_karnataka_rental_guidance_tool() -> dict[str, Any]:
    refs = get_karnataka_rental_guidance()
    return {
        "status": "complete",
        "agent_note": "Legal sources delivered — summarize; do not call this tool again this turn.",
        "sources": [r.model_dump() for r in refs],
    }


def create_anonymous_experience_tool(
    locality: str,
    property_type: str,
    category: str,
    sentiment: str,
    experience_text: str,
    rent_band: str = "",
    move_period: str = "",
) -> dict[str, Any]:
    data = AnonymousExperienceInput(
        locality=locality,
        property_type=property_type,
        category=category,
        sentiment=sentiment,
        experience_text=experience_text,
        rent_band=rent_band or None,
        move_period=move_period or None,
    )
    return create_anonymous_experience(data)


def search_anonymous_experiences_tool(
    locality: str = "",
    category: str = "",
    property_type: str = "",
    sentiment: str = "",
) -> dict[str, Any]:
    return search_anonymous_experiences(
        locality=locality or None,
        category=category or None,
        property_type=property_type or None,
        sentiment=sentiment or None,
    )


def report_community_content_tool(
    content_type: str,
    content_public_id: str,
    reason: str,
) -> dict[str, Any]:
    return report_community_content(content_type, content_public_id, reason)


def create_vacating_post_tool(
    locality: str,
    property_type: str,
    room_type: str,
    monthly_rent_inr: int,
    availability_date: str,
    post_kind: str,
    description: str,
    contact_method: str,
    deposit_inr: int = 0,
    furnishing: str = "",
    publish: bool = True,
    owner_permission_ack: bool = False,
) -> dict[str, Any]:
    from datetime import date as date_cls

    data = VacatingPostInput(
        locality=locality,
        property_type=property_type,
        room_type=room_type,
        monthly_rent_inr=monthly_rent_inr,
        deposit_inr=deposit_inr or None,
        availability_date=date_cls.fromisoformat(availability_date),
        furnishing=furnishing or None,
        post_kind=post_kind,
        description=description,
        contact_method=contact_method,
        owner_permission_ack=owner_permission_ack,
    )
    return create_vacating_post(data, publish=publish)


def search_available_rooms_tool(
    locality: str = "",
    room_type: str = "",
    max_rent_inr: int = 0,
) -> dict[str, Any]:
    return search_available_rooms(
        locality=locality or None,
        room_type=room_type or None,
        max_rent_inr=max_rent_inr or None,
    )


def update_vacating_post_status_tool(
    public_id: str,
    edit_token: str,
    status: str,
    availability_date: str = "",
) -> dict[str, Any]:
    from datetime import date as date_cls

    ad = date_cls.fromisoformat(availability_date) if availability_date else None
    return update_vacating_post_status(public_id, edit_token, status, availability_date=ad)


def generate_rental_safety_report_tool(
    listing_text: str,
    chat_text: str = "",
    locality: str = "",
) -> dict[str, Any]:
    report = generate_rental_safety_report(listing_text, chat_text or None, locality_hint=locality or None)
    return report.model_dump()


ALL_TOOL_FUNCTIONS = [
    analyze_rental_listing,
    detect_rental_red_flags,
    estimate_bengaluru_rent_tool,
    assess_deposit_terms_tool,
    build_rental_checklist_tool,
    get_karnataka_rental_guidance_tool,
    create_anonymous_experience_tool,
    search_anonymous_experiences_tool,
    report_community_content_tool,
    create_vacating_post_tool,
    search_available_rooms_tool,
    update_vacating_post_status_tool,
    generate_rental_safety_report_tool,
]

"""
Core Orchestration Agent for NammaRaktha.
Coordinates requirement parsing, clinical compatibility, blood bank matching,
and bilingual SOS broadcast generation.
"""

from typing import Optional
from .models import (
    PatientRequirement,
    AgentTriageResult,
    BloodComponent,
    BloodGroup,
    UrgencyLevel,
    BangaloreZone
)
from .gemini_client import parse_patient_requirement
from .compatibility import get_compatible_donors
from .blood_banks import match_blood_banks
from .sos_generator import generate_sos_message
from .db import find_matching_donors, log_emergency
from .guardrails import check_input_guardrails, validate_patient_requirement


class NammaRakthaAgent:
    """
    Bengaluru Emergency Blood & Platelet Donor Coordination Agent.
    """

    def __init__(self):
        pass

    def triage(
        self,
        raw_text: str,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/jpeg"
    ) -> AgentTriageResult:
        """
        Executes end-to-end emergency blood triage pipeline with strict guardrails
        and clinical missing-information validation.
        """
        # Step 0: Scope & Safety Guardrails Check
        guardrail_check = check_input_guardrails(raw_text)
        if not guardrail_check.is_safe:
            dummy_req = PatientRequirement(
                blood_group=BloodGroup.O_POS,
                component=BloodComponent.WHOLE_BLOOD,
                hospital_name="Bengaluru Coordination Center",
                contact_phone="+91 00000 00000"
            )
            dummy_comp = get_compatible_donors(dummy_req.blood_group, dummy_req.component)
            dummy_sos = generate_sos_message(dummy_req, dummy_comp)
            return AgentTriageResult(
                requirement=dummy_req,
                compatibility=dummy_comp,
                matched_blood_banks=[],
                matched_donors=[],
                sos=dummy_sos,
                actionable_advice=guardrail_check.violation_reason or "Request blocked by safety guardrails.",
                is_guardrail_blocked=True,
                guardrail_message=guardrail_check.violation_reason
            )

        # Step 1: Parse requirement (Gemini 2.5 Flash / Fallback)
        req: PatientRequirement = parse_patient_requirement(
            raw_text=raw_text,
            image_bytes=image_bytes,
            mime_type=mime_type
        )

        # Step 2: Validate Requisition for Missing Information
        validation_warnings = validate_patient_requirement(req, raw_text)

        # Step 3: Clinical Compatibility & Donor Rules
        comp = get_compatible_donors(
            recipient=req.blood_group,
            component=req.component
        )

        # Step 4: Match Bengaluru Blood Banks
        needs_apheresis = req.component in [
            BloodComponent.PLATELETS_SDP,
            BloodComponent.PLATELETS_RDP
        ]
        matched_banks = match_blood_banks(
            zone=req.zone,
            needs_apheresis=needs_apheresis,
            max_results=4
        )

        # Step 5: Query Registered Voluntary Donors from Database
        matched_donors = find_matching_donors(
            compatible_groups=comp.compatible_donor_groups,
            patient_zone=req.zone,
            needs_sdp=needs_apheresis,
            limit=4
        )

        # Step 6: Bilingual SOS Broadcast Generation
        sos = generate_sos_message(req=req, comp=comp)

        # Step 7: Log emergency in SQLite database
        try:
            log_emergency(req)
        except Exception:
            pass

        # Step 8: Actionable Operational Guidance
        top_bank = matched_banks[0] if matched_banks else None
        top_bank_str = f"{top_bank.name} ({top_bank.phone})" if top_bank else "Nearest blood bank"
        
        advice_parts = [
            f"1. Call {top_bank_str} immediately to check current stock before dispatching voluntary donors.",
            f"2. For {req.component.value}: Ensure volunteer donor has not consumed alcohol in 24 hours.",
        ]
        if needs_apheresis:
            advice_parts.append("3. For Single Donor Platelets (SDP): Confirm the donor has taken NO Aspirin/NSAIDs in last 72 hours.")
        advice_parts.append(f"4. Share the 1-click WhatsApp broadcast to Bengaluru local community and alumni groups.")
        advice_parts.append(f"5. Transit Advisory: {top_bank.peak_traffic_advisory if top_bank else 'Account for peak congestion.'}")

        actionable_advice = "\n".join(advice_parts)

        return AgentTriageResult(
            requirement=req,
            compatibility=comp,
            matched_blood_banks=matched_banks,
            matched_donors=matched_donors,
            sos=sos,
            actionable_advice=actionable_advice,
            validation_warnings=validation_warnings,
            is_guardrail_blocked=False
        )


# Global default instance
agent = NammaRakthaAgent()

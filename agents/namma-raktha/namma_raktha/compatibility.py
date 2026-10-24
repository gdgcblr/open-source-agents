"""
Clinical Blood & Component Compatibility Matrix with Apheresis Donor Rules.
Compliant with National Blood Transfusion Council (NBTC) India guidelines.
"""

from typing import List
from .models import BloodGroup, BloodComponent, CompatibilityResult


def get_compatible_donors(recipient: BloodGroup, component: BloodComponent) -> CompatibilityResult:
    """
    Computes compatible donor blood groups and clinical eligibility criteria
    based on the required blood component and recipient group.
    """
    clinical_notes: List[str] = []
    eligibility_criteria: List[str] = [
        "Age between 18 and 60 years (first-time donors up to 60, regular up to 65)",
        "Minimum body weight: 45 kg for whole blood, 50-55 kg for apheresis (SDP platelets)",
        "Hemoglobin minimum: 12.5 g/dL (tested on site)",
        "Pulse: 60-100 bpm, Blood pressure within normal clinical limits",
        "No alcohol consumption in the past 24 hours",
        "Adequate sleep (>6 hours) and light meal before donation (do not come empty stomach)"
    ]

    # Special rules for Bombay Blood Group
    if recipient == BloodGroup.BOMBAY:
        compatible = [BloodGroup.BOMBAY]
        clinical_notes.append("CRITICAL: Patient has extremely rare Bombay Blood Group (hh phenotype).")
        clinical_notes.append("Cannot receive regular O-negative; patient possesses anti-H antibodies.")
        clinical_notes.append("Immediately alert Sankalp India Foundation (Toll-Free Bangalore) & Rotary TTK Rare Blood Registry.")
        return CompatibilityResult(
            recipient_group=recipient,
            component=component,
            compatible_donor_groups=compatible,
            ideal_donor_group=BloodGroup.BOMBAY,
            universal_donor_for_type="Only another Bombay (hh) donor",
            clinical_notes=clinical_notes,
            donor_eligibility_criteria=eligibility_criteria
        )

    # 1. Plasma (FFP) Compatibility - Opposite of RBC!
    if component == BloodComponent.FRESH_FROZEN_PLASMA:
        plasma_matrix = {
            BloodGroup.O_POS: [BloodGroup.O_POS, BloodGroup.O_NEG, BloodGroup.A_POS, BloodGroup.A_NEG, BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.O_NEG: [BloodGroup.O_POS, BloodGroup.O_NEG, BloodGroup.A_POS, BloodGroup.A_NEG, BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.A_POS: [BloodGroup.A_POS, BloodGroup.A_NEG, BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.A_NEG: [BloodGroup.A_POS, BloodGroup.A_NEG, BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.B_POS: [BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.B_NEG: [BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.AB_POS: [BloodGroup.AB_POS, BloodGroup.AB_NEG],
            BloodGroup.AB_NEG: [BloodGroup.AB_POS, BloodGroup.AB_NEG],
        }
        compatible = plasma_matrix.get(recipient, [recipient])
        clinical_notes.append("Notice: Plasma compatibility is inverted compared to RBCs.")
        clinical_notes.append("AB is the Universal Plasma Donor (contains no anti-A or anti-B antibodies).")
        return CompatibilityResult(
            recipient_group=recipient,
            component=component,
            compatible_donor_groups=compatible,
            ideal_donor_group=recipient,
            universal_donor_for_type="AB+ / AB- (Universal Plasma Donor)",
            clinical_notes=clinical_notes,
            donor_eligibility_criteria=eligibility_criteria
        )

    # 2. Platelets (SDP / RDP) Compatibility
    if component in [BloodComponent.PLATELETS_SDP, BloodComponent.PLATELETS_RDP]:
        platelet_matrix = {
            BloodGroup.O_POS: [BloodGroup.O_POS, BloodGroup.O_NEG, BloodGroup.A_POS, BloodGroup.B_POS],
            BloodGroup.O_NEG: [BloodGroup.O_NEG, BloodGroup.O_POS],
            BloodGroup.A_POS: [BloodGroup.A_POS, BloodGroup.A_NEG, BloodGroup.AB_POS],
            BloodGroup.A_NEG: [BloodGroup.A_NEG, BloodGroup.A_POS],
            BloodGroup.B_POS: [BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.AB_POS],
            BloodGroup.B_NEG: [BloodGroup.B_NEG, BloodGroup.B_POS],
            BloodGroup.AB_POS: [BloodGroup.AB_POS, BloodGroup.AB_NEG, BloodGroup.A_POS, BloodGroup.B_POS],
            BloodGroup.AB_NEG: [BloodGroup.AB_NEG, BloodGroup.AB_POS],
        }
        compatible = platelet_matrix.get(recipient, [recipient])
        clinical_notes.append("Identical ABO match is always strongly preferred for Single Donor Platelets (SDP).")
        clinical_notes.append("ABO-incompatible platelets can be issued in acute emergency if titer is acceptable.")
        
        # Specific strict criteria for SDP Apheresis donors
        eligibility_criteria.extend([
            "MUST NOT have taken Aspirin, Disprin, Ibuprofen, or any NSAID within the last 48-72 hours (causes platelet dysfunction)",
            "Weight strictly > 50 kg (many Bangalore apheresis centers require > 55 kg)",
            "Good, visible, non-collapsible peripheral arm veins (procedure takes 60-90 minutes on cell separator machine)",
            "Platelet count must be > 150,000 / μL (pre-tested via CBC before hookup)",
            "At least 48 hours gap since previous plateletpheresis donation (maximum 24 times per year)"
        ])
        return CompatibilityResult(
            recipient_group=recipient,
            component=component,
            compatible_donor_groups=compatible,
            ideal_donor_group=recipient,
            universal_donor_for_type="AB+ / O- (ABO-matched is safest)",
            clinical_notes=clinical_notes,
            donor_eligibility_criteria=eligibility_criteria
        )

    # 3. Whole Blood and Packed Red Blood Cells (PRBC)
    rbc_matrix = {
        BloodGroup.O_NEG: [BloodGroup.O_NEG],
        BloodGroup.O_POS: [BloodGroup.O_POS, BloodGroup.O_NEG],
        BloodGroup.A_NEG: [BloodGroup.A_NEG, BloodGroup.O_NEG],
        BloodGroup.A_POS: [BloodGroup.A_POS, BloodGroup.A_NEG, BloodGroup.O_POS, BloodGroup.O_NEG],
        BloodGroup.B_NEG: [BloodGroup.B_NEG, BloodGroup.O_NEG],
        BloodGroup.B_POS: [BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.O_POS, BloodGroup.O_NEG],
        BloodGroup.AB_NEG: [BloodGroup.AB_NEG, BloodGroup.A_NEG, BloodGroup.B_NEG, BloodGroup.O_NEG],
        BloodGroup.AB_POS: [
            BloodGroup.AB_POS, BloodGroup.AB_NEG,
            BloodGroup.A_POS, BloodGroup.A_NEG,
            BloodGroup.B_POS, BloodGroup.B_NEG,
            BloodGroup.O_POS, BloodGroup.O_NEG
        ],
    }

    compatible = rbc_matrix.get(recipient, [recipient])
    if recipient == BloodGroup.O_NEG:
        clinical_notes.append("O-Negative is the Universal Red Cell Donor, but can ONLY receive O-Negative.")
        clinical_notes.append("Check Rotary TTK and Rashtrotthana emergency rare donor wings immediately.")
    elif recipient == BloodGroup.AB_POS:
        clinical_notes.append("AB-Positive is the Universal Red Cell Recipient and can receive all 8 ABO/Rh types.")
    else:
        clinical_notes.append(f"Primary match: {recipient.value}. Acceptable compatible alternatives: {', '.join(g.value for g in compatible if g != recipient)}.")

    eligibility_criteria.extend([
        "At least 3 months gap (90 days for men, 120 days for women) since last whole blood donation",
        "No tattoos, body piercing, or acupuncture in the past 6 months",
        "No major surgery in past 6 months or minor dental procedure in past 72 hours",
        "Female donors: Not pregnant, lactating, or within menstrual flow period"
    ])

    return CompatibilityResult(
        recipient_group=recipient,
        component=component,
        compatible_donor_groups=compatible,
        ideal_donor_group=recipient,
        universal_donor_for_type="O-Negative (Universal Red Cell Donor)",
        clinical_notes=clinical_notes,
        donor_eligibility_criteria=eligibility_criteria
    )

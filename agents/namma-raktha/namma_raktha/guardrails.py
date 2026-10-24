"""
Safety Guardrails & Clinical Query Validation Engine for NammaRaktha.
Ensures agent operates strictly within safe clinical scope, defends against prompt injection,
flags illegal blood commerce/scams, and identifies missing critical requisition details.
"""

import re
from typing import List
from .models import PatientRequirement, ValidationWarning, GuardrailCheckResult


# Scope keywords (at least one must be conceptually present or emergency implied)
BLOOD_DOMAIN_KEYWORDS = [
    "blood", "platelet", "platelets", "sdp", "rdp", "plasma", "ffp", "prbc",
    "transfusion", "donor", "donors", "donate", "hospital", "icu", "dengue",
    "leukemia", "anemia", "accident", "trauma", "surgery", "hemoglobin",
    "a+", "a-", "b+", "b-", "ab+", "ab-", "o+", "o-", "bombay", "units", "unit"
]

# Prompt injection and malicious evasion patterns
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s*prompt",
    r"disregard\s+(all\s+)?rules",
    r"you\s+are\s+now\s+(a|an)?\s*[a-z]+",
    r"jailbreak",
    r"\bDAN\b",
    r"bypass\s+(the\s+)?sandbox",
    r"give\s+me\s+your\s+api\s*key",
]

# Anti-commercialization / paid blood scam keywords (Illegal under National Blood Policy India)
COMMERCIAL_SCAM_PATTERNS = [
    r"sell\s+(blood|platelets)",
    r"buy\s+(blood|platelets)",
    r"rate\s+per\s+(unit|bottle|bag)",
    r"price\s+(of|per)\s+(blood|platelet)",
    r"cost\s+of\s+(blood|platelet)",
    r"pay\s+\d+\s*(rs|inr|rupees)",
    r"advance\s+payment",
    r"transfer\s+to\s+upi",
    r"gpay\s+number",
    r"phonepe\s+number",
]


def check_input_guardrails(raw_text: str) -> GuardrailCheckResult:
    """
    Enforces scope, injection defense, and commercial scam protection.
    """
    text_clean = raw_text.strip().lower()

    # 1. Prompt Injection Defense
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_clean):
            return GuardrailCheckResult(
                is_safe=False,
                violation_reason=(
                    "Security Guardrail Triggered: Adversarial prompt manipulation detected. "
                    "NammaRaktha is strictly bounded to emergency blood and platelet coordination."
                )
            )

    # 2. Anti-Commercialization & Scam Defense (Legal NBTC Mandate)
    for pattern in COMMERCIAL_SCAM_PATTERNS:
        if re.search(pattern, text_clean):
            return GuardrailCheckResult(
                is_safe=False,
                is_commercial_scam=True,
                violation_reason=(
                    "Legal & Ethical Guardrail: Buying, selling, or offering monetary compensation for human blood "
                    "is strictly illegal in India under the National Blood Transfusion Policy and Supreme Court orders. "
                    "NammaRaktha exclusively supports voluntary, non-remunerated donation."
                )
            )

    # 3. Off-Topic / General Chat Defense
    has_domain_keyword = any(k in text_clean for k in BLOOD_DOMAIN_KEYWORDS)
    if not has_domain_keyword and len(text_clean.split()) > 3:
        return GuardrailCheckResult(
            is_safe=False,
            is_off_topic=True,
            violation_reason=(
                "Scope Guardrail: Input appears unrelated to blood or platelet requirements. "
                "Please enter a valid patient transfusion need (e.g. required blood group, hospital name, units)."
            )
        )

    return GuardrailCheckResult(is_safe=True)


def validate_patient_requirement(req: PatientRequirement, raw_text: str) -> List[ValidationWarning]:
    """
    Analyzes the extracted requirement and flags missing or underspecified clinical info.
    """
    warnings: List[ValidationWarning] = []
    text_lower = raw_text.lower()

    # 1. Missing or Placeholder Contact Phone
    phone_clean = re.sub(r"[^\d]", "", req.contact_phone)
    if not phone_clean or len(phone_clean) < 10 or "12345" in phone_clean:
        warnings.append(ValidationWarning(
            field="Contact Phone",
            severity="critical",
            message="No verified 10-digit attendant phone number detected.",
            action_needed="Add a working mobile number so donors and blood banks can reach the patient family immediately."
        ))

    # 2. Generic or Missing Hospital Name
    if any(h in req.hospital_name.lower() for h in ["city hospital", "bengaluru hospital", "unknown"]):
        warnings.append(ValidationWarning(
            field="Hospital Location",
            severity="warning",
            message="Hospital name is generic or unspecified.",
            action_needed="Specify the exact hospital (e.g. Manipal Old Airport Rd, Victoria BMCRI, Aster CMI) so transit time can be computed accurately."
        ))

    # 3. Missing IP / Case Number
    if not req.case_or_ip_number or req.case_or_ip_number.startswith("IP-"):
        warnings.append(ValidationWarning(
            field="In-Patient (IP) Number",
            severity="info",
            message="Hospital IP / Ward number is missing.",
            action_needed="Ask the hospital desk for the IP number. Blood banks require this before releasing cross-matched units."
        ))

    # 4. Dengue Component Mismatch Check
    if "dengue" in text_lower and "platelet" not in req.component.value.lower():
        warnings.append(ValidationWarning(
            field="Component Verification",
            severity="warning",
            message="Dengue mentioned, but component is set to Whole Blood.",
            action_needed="Dengue patients typically require Single Donor Platelets (SDP). Please confirm with treating doctor."
        ))

    return warnings

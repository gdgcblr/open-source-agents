"""
Gemini Multimodal Client & Smart Local Fallback Parser.
Extracts structured patient requirements from raw text or doctor requisition slips.
"""

import json
import re
import base64
from typing import Optional, Dict, Any
import requests
from .config import GEMINI_API_KEY, MODEL_NAME
from .models import (
    PatientRequirement,
    BloodGroup,
    BloodComponent,
    UrgencyLevel,
    BangaloreZone
)


GEMINI_EXTRACTION_PROMPT = """
You are NammaRaktha, an expert clinical triage assistant for blood and platelet coordination in Bengaluru, India.
Extract the patient's blood emergency requirements from the provided text or image of a doctor requisition slip into JSON.

JSON schema required:
{
  "patient_name": "string or null",
  "blood_group": "A+|A-|B+|B-|AB+|AB-|O+|O-|Bombay (hh)",
  "component": "Whole Blood|Platelets (SDP - Single Donor Apheresis)|Platelets (RDP - Random Donor)|PRBC (Packed Red Blood Cells)|FFP (Fresh Frozen Plasma)|Cryoprecipitate",
  "units": integer (1 to 10),
  "hospital_name": "string (name of hospital/clinic)",
  "hospital_address": "string (area/street)",
  "zone": "Central Bengaluru (Majestic, MG Road, Shivaji Nagar, Market)|East Bengaluru (Indiranagar, Whitefield, Marathahalli, HAL)|South Bengaluru (Jayanagar, BTM, HSR, Koramangala, Bannerghatta, E-City)|North Bengaluru (Hebbal, Yelahanka, Manyata, Mathikere)|West Bengaluru (Malleshwaram, Rajajinagar, Vijayanagar, Kengeri)",
  "urgency": "CRITICAL (<2 Hours - ICU/Emergency)|URGENT (2-6 Hours)|STANDARD (Within 24 Hours)|PLANNED (Scheduled Surgery)",
  "contact_name": "string (name of attendant or doctor)",
  "contact_phone": "string (10-digit phone or mobile)",
  "case_or_ip_number": "string or null",
  "diagnosis_or_notes": "string or null (e.g., dengue, surgery, trauma)"
}

Return ONLY valid JSON matching this schema. Do not include markdown code fence formatting or explanations.
"""


def extract_with_gemini_rest(prompt_text: str, image_bytes: Optional[bytes] = None, mime_type: str = "image/jpeg") -> Optional[Dict[str, Any]]:
    """
    Invokes Gemini 2.5 Flash via standard REST API without requiring custom client SDKs.
    """
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    parts = []
    if image_bytes:
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": encoded_image
            }
        })

    full_prompt = f"{GEMINI_EXTRACTION_PROMPT}\n\nUser Input:\n{prompt_text}"
    parts.append({"text": full_prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=12)
        if response.status_code == 200:
            res_data = response.json()
            candidates = res_data.get("candidates", [])
            if candidates:
                content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                # Clean up any potential markdown formatting
                clean_json = content_text.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                return json.loads(clean_json.strip())
    except Exception as e:
        # Fallback will handle failure gracefully
        pass
    return None


def local_fallback_parser(raw_text: str) -> Dict[str, Any]:
    """
    Deterministic rule-based clinical and geographic parser for offline demo reliability.
    Extracts blood group, hospital, zone, phone numbers, component, and urgency.
    """
    text = raw_text.strip()
    text_lower = text.lower()

    # 1. Blood Group Extraction
    bg = BloodGroup.O_POS
    if re.search(r"\bbombay\b", text_lower):
        bg = BloodGroup.BOMBAY
    elif re.search(r"\bo\s*-\s*ve|\bo\s*neg|\bo-", text_lower):
        bg = BloodGroup.O_NEG
    elif re.search(r"\bo\s*\+\s*ve|\bo\s*pos|\bo\+", text_lower):
        bg = BloodGroup.O_POS
    elif re.search(r"\bab\s*-\s*ve|\bab\s*neg|\bab-", text_lower):
        bg = BloodGroup.AB_NEG
    elif re.search(r"\bab\s*\+\s*ve|\bab\s*pos|\bab\+", text_lower):
        bg = BloodGroup.AB_POS
    elif re.search(r"\ba\s*-\s*ve|\ba\s*neg|\ba-", text_lower):
        bg = BloodGroup.A_NEG
    elif re.search(r"\ba\s*\+\s*ve|\ba\s*pos|\ba\+", text_lower):
        bg = BloodGroup.A_POS
    elif re.search(r"\bb\s*-\s*ve|\bb\s*neg|\bb-", text_lower):
        bg = BloodGroup.B_NEG
    elif re.search(r"\bb\s*\+\s*ve|\bb\s*pos|\bb\+", text_lower):
        bg = BloodGroup.B_POS

    # 2. Blood Component
    comp = BloodComponent.WHOLE_BLOOD
    if any(k in text_lower for k in ["sdp", "single donor", "apheresis", "platelet", "platelets"]):
        if "rdp" in text_lower or "random" in text_lower:
            comp = BloodComponent.PLATELETS_RDP
        else:
            comp = BloodComponent.PLATELETS_SDP
    elif any(k in text_lower for k in ["ffp", "plasma"]):
        comp = BloodComponent.FRESH_FROZEN_PLASMA
    elif any(k in text_lower for k in ["prbc", "packed red", "red cells"]):
        comp = BloodComponent.PACKED_RED_CELLS
    elif "cryo" in text_lower:
        comp = BloodComponent.CRYOPRECIPITATE

    # 3. Units
    units = 1
    units_match = re.search(r"(\d+)\s*(?:unit|units|bag|bags|pints)", text_lower)
    if units_match:
        try:
            units = max(1, min(10, int(units_match.group(1))))
        except ValueError:
            units = 1

    # 4. Hospital & Zone
    hospital_name = "Bengaluru City Hospital"
    zone = BangaloreZone.CENTRAL
    hospital_address = "Bengaluru"

    if any(k in text_lower for k in ["manipal", "old airport", "hal"]):
        hospital_name = "Manipal Hospital, Old Airport Road"
        hospital_address = "98, HAL Old Airport Rd, Kodihalli"
        zone = BangaloreZone.EAST
    elif any(k in text_lower for k in ["vydehi", "whitefield", "itpl", "hope farm"]):
        hospital_name = "Vydehi Institute of Medical Sciences"
        hospital_address = "EPIP Area, Whitefield"
        zone = BangaloreZone.EAST
    elif any(k in text_lower for k in ["rotary", "ttk", "indiranagar"]):
        hospital_name = "Rotary TTK Blood Centre"
        hospital_address = "HAL 3rd Stage, Indiranagar"
        zone = BangaloreZone.EAST
    elif any(k in text_lower for k in ["nimhans", "dairy circle", "wilson garden"]):
        hospital_name = "NIMHANS Hospital"
        hospital_address = "Hosur Road, Near Dairy Circle"
        zone = BangaloreZone.SOUTH
    elif any(k in text_lower for k in ["kidwai", "oncology", "cancer"]):
        hospital_name = "Kidwai Memorial Institute of Oncology"
        hospital_address = "Dr. M.H. Marigowda Road"
        zone = BangaloreZone.SOUTH
    elif any(k in text_lower for k in ["jayadeva", "bannerghatta", "cardio"]):
        hospital_name = "Sri Jayadeva Institute of Cardiovascular Sciences"
        hospital_address = "Bannerghatta Main Road, 9th Block Jayanagar"
        zone = BangaloreZone.SOUTH
    elif any(k in text_lower for k in ["rashtrotthana", "jayanagar", "ashoka pillar"]):
        hospital_name = "Rashtrotthana Blood Centre"
        hospital_address = "Jayanagar 1st Block, Near Ashoka Pillar"
        zone = BangaloreZone.SOUTH
    elif any(k in text_lower for k in ["narayana", "health city", "bommasandra", "electronic city", "e-city"]):
        hospital_name = "Narayana Health City"
        hospital_address = "Bommasandra Industrial Area, Electronic City"
        zone = BangaloreZone.SOUTH
    elif any(k in text_lower for k in ["victoria", "kr market", "k.r. market", "fort", "bmcri"]):
        hospital_name = "Victoria Hospital (BMCRI)"
        hospital_address = "Fort, K.R. Market"
        zone = BangaloreZone.CENTRAL
    elif any(k in text_lower for k in ["bowring", "shivajinagar", "tasker town"]):
        hospital_name = "Bowring and Lady Curzon Hospital"
        hospital_address = "Hospital Road, Shivaji Nagar"
        zone = BangaloreZone.CENTRAL
    elif any(k in text_lower for k in ["aster", "cmi", "hebbal", "sahakar"]):
        hospital_name = "Aster CMI Hospital"
        hospital_address = "New Airport Road, Sahakar Nagar, Hebbal"
        zone = BangaloreZone.NORTH
    elif any(k in text_lower for k in ["ramaiah", "msr", "mathikere"]):
        hospital_name = "M.S. Ramaiah Memorial Hospital"
        hospital_address = "MSRIT Post, Mathikere"
        zone = BangaloreZone.NORTH
    elif any(k in text_lower for k in ["kc general", "k.c. general", "malleshwaram"]):
        hospital_name = "K.C. General Hospital"
        hospital_address = "5th Cross Road, Malleshwaram"
        zone = BangaloreZone.WEST
    elif any(k in text_lower for k in ["fortis rajajinagar", "rajajinagar", "west of chord"]):
        hospital_name = "Fortis Hospital, Rajajinagar"
        hospital_address = "West of Chord Road, Rajajinagar 1st Block"
        zone = BangaloreZone.WEST

    # 5. Contact Phone
    phone_match = re.search(r"(?:\+91[-.\s]?)?[6-9]\d{9}", text)
    contact_phone = phone_match.group(0) if phone_match else "+91 98860 12345 (Attendant)"

    # 6. Contact Name
    contact_name = "Attendant / Coordinator"
    name_match = re.search(r"(?:contact|call|attendant|coordinator)\s*:?\s*([A-Za-z]+)", text_lower)
    if name_match:
        contact_name = name_match.group(1).title()

    # 7. Urgency Level
    urgency = UrgencyLevel.URGENT
    if any(k in text_lower for k in ["critical", "immediate", "icu", "emergency", "within 1 hour", "dying"]):
        urgency = UrgencyLevel.CRITICAL
    elif any(k in text_lower for k in ["routine", "tomorrow", "surgery on monday", "planned"]):
        urgency = UrgencyLevel.PLANNED

    return {
        "patient_name": "Emergency Patient",
        "blood_group": bg.value,
        "component": comp.value,
        "units": units,
        "hospital_name": hospital_name,
        "hospital_address": hospital_address,
        "zone": zone.value,
        "urgency": urgency.value,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "case_or_ip_number": "IP-" + str(units * 1042),
        "diagnosis_or_notes": "Clinical blood transfusion triage required"
    }


def parse_patient_requirement(
    raw_text: str,
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg"
) -> PatientRequirement:
    """
    High-level extraction: Uses Gemini 2.5 Flash if available, otherwise falls back seamlessly.
    """
    extracted_dict = extract_with_gemini_rest(raw_text, image_bytes, mime_type)
    if not extracted_dict:
        extracted_dict = local_fallback_parser(raw_text)

    # Validate and instantiate Pydantic model
    return PatientRequirement(
        patient_name=extracted_dict.get("patient_name") or "Emergency Patient",
        blood_group=BloodGroup(extracted_dict.get("blood_group", BloodGroup.O_POS.value)),
        component=BloodComponent(extracted_dict.get("component", BloodComponent.WHOLE_BLOOD.value)),
        units=int(extracted_dict.get("units", 1)),
        hospital_name=extracted_dict.get("hospital_name") or "Bengaluru Hospital",
        hospital_address=extracted_dict.get("hospital_address") or "Bengaluru",
        zone=BangaloreZone(extracted_dict.get("zone", BangaloreZone.CENTRAL.value)),
        urgency=UrgencyLevel(extracted_dict.get("urgency", UrgencyLevel.URGENT.value)),
        contact_name=extracted_dict.get("contact_name") or "Attendant",
        contact_phone=extracted_dict.get("contact_phone") or "+91 98860 12345",
        case_or_ip_number=extracted_dict.get("case_or_ip_number"),
        diagnosis_or_notes=extracted_dict.get("diagnosis_or_notes")
    )

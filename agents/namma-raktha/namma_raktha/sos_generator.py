"""
Clean, Professional WhatsApp & Twitter SOS Generator.
Generates clean, readable short links (no ugly %20 encoded URL blobs)
and exports WhatsApp Cloud API Interactive Button JSON payload.
"""

import re
import urllib.parse
from .models import PatientRequirement, CompatibilityResult, SOSMessage


def generate_sos_message(req: PatientRequirement, comp: CompatibilityResult) -> SOSMessage:
    """
    Builds clean, non-spam emergency broadcasts with clean short URLs
    that render cleanly in WhatsApp without link clutter.
    """
    compatible_groups_str = ", ".join(g.value for g in comp.compatible_donor_groups)
    ip_str = f" (IP: {req.case_or_ip_number})" if req.case_or_ip_number else ""
    patient_display = req.patient_name if req.patient_name else "Patient"
    location_str = req.hospital_address if req.hospital_address else req.zone.value.split("(")[0].strip()

    # Clean phone digits
    phone_digits = re.sub(r"[^\d]", "", req.contact_phone)
    if len(phone_digits) == 10:
        phone_digits = "91" + phone_digits
    elif phone_digits.startswith("0"):
        phone_digits = "91" + phone_digits[1:]

    # Clean, concise 1-line Google Maps link (no %20 garbage)
    clean_map_query = "+".join(req.hospital_name.replace(",", " ").replace(".", " ").split()[:4]) + "+Bengaluru"
    clean_map_url = f"https://maps.google.com/?q={clean_map_query}"

    # Clean, concise 1-line Donor Accept Link (renders as clean 1-line wa.me link)
    clean_bg = req.blood_group.value.replace("(", "").replace(")", "").replace(" ", "+")
    if clean_bg.endswith("+"):
        clean_bg = clean_bg[:-1] + "%2B"
    clean_accept_url = f"https://wa.me/{phone_digits}?text=I+can+donate+{clean_bg}" if phone_digits else ""

    # 1. Clean Professional WhatsApp Broadcast (Zero link clutter)
    english_lines = [
        "🚨 *URGENT BLOOD REQUIREMENT - BENGALURU*",
        "",
        f"• *Hospital:* {req.hospital_name}",
        f"• *Location:* {location_str}",
        f"• *Blood Group:* *{req.blood_group.value}*",
        f"• *Component:* {req.component.value}",
        f"• *Units Required:* {req.units}",
        f"• *Compatible Donors:* {compatible_groups_str}",
        f"• *Patient:* {patient_display}{ip_str}",
        f"• *Contact Attendant:* *{req.contact_name}* - *{req.contact_phone}*",
        "",
        f"📍 *Hospital Map:* {clean_map_url}",
    ]

    if "Platelet" in req.component.value or "SDP" in req.component.value:
        english_lines.append("")
        english_lines.append("*Platelet Criteria:* Donor must weigh >50kg and have NO Aspirin/NSAIDs in last 72 hours.")

    if clean_accept_url:
        english_lines.append("")
        english_lines.append("👉 *Can you donate? Tap to confirm:*")
        english_lines.append(clean_accept_url)

    english_lines.extend([
        "",
        "Verified via NammaRaktha Bengaluru.",
        "Please confirm with the attendant before dispatching donors."
    ])
    english_text = "\n".join(english_lines)

    # 2. Clean Kannada Broadcast
    kannada_lines = [
        "🚨 *ತುರ್ತು ರಕ್ತದ ಅವಶ್ಯಕತೆ - ಬೆಂಗಳೂರು*",
        "",
        f"• ಆಸ್ಪತ್ರೆ: {req.hospital_name}",
        f"• ಸ್ಥಳ: {location_str}",
        f"• ರಕ್ತದ ಗುಂಪು: *{req.blood_group.value}* ({req.component.value})",
        f"• ಘಟಕಗಳು: {req.units}",
        f"• ಹೊಂದಾಣಿಕೆಯಾಗುವ ದಾನಿಗಳು: {compatible_groups_str}",
        f"• ಸಂಪರ್ಕ: *{req.contact_name}* - *{req.contact_phone}*",
        f"• ಮ್ಯಾಪ್: {clean_map_url}",
        "",
        "ದಯವಿಟ್ಟು ಅರ್ಹ ರಕ್ತದಾನಿಗಳೊಂದಿಗೆ ಹಂಚಿಕೊಳ್ಳಿ • ನಮ್ಮರಕ್ತ"
    ]
    kannada_text = "\n".join(kannada_lines)

    # 3. Clean Phonetic Kannada
    phonetic_lines = [
        "🚨 *THURTHU RAKTHADA AVASHYAKATHE - BENGALURU*",
        f"Hospital: {req.hospital_name}",
        f"Blood Group: {req.blood_group.value} ({req.component.value})",
        f"Map: {clean_map_url}",
        f"Contact: {req.contact_name} - {req.contact_phone}",
        "Eligible donors please call or message directly."
    ]
    kannada_phonetic = "\n".join(phonetic_lines)

    # 4. WhatsApp Share URL
    encoded_wa = urllib.parse.quote(english_text)
    whatsapp_share_url = f"https://api.whatsapp.com/send?text={encoded_wa}"

    # 5. Clean, Professional Twitter / X Post (Strictly under 280 chars)
    short_hospital = req.hospital_name.replace("Hospital", "Hosp").replace("Institute of", "Inst")[:30]
    twitter_text = (
        f"URGENT #Bengaluru: {req.blood_group.value} {req.component.value} ({req.units} units) "
        f"needed at {short_hospital}.\n"
        f"Compatible: {compatible_groups_str}\n"
        f"Contact: {req.contact_phone} ({req.contact_name})\n"
        f"Pls RT @BangaloreBlood @BloodDonorsIn #NammaRaktha"
    )
    encoded_tw = urllib.parse.quote(twitter_text)
    twitter_share_url = f"https://twitter.com/intent/tweet?text={encoded_tw}"

    verification_checklist = [
        "Confirm patient's hospital registration / IP number with hospital reception.",
        "Check that doctor has written a formal cross-matching requisition form.",
        "Verify donor has not consumed alcohol in the last 24 hours.",
        "For platelet (SDP) donors: Verify no Aspirin/painkillers taken in last 72 hours."
    ]

    # 6. Official WhatsApp Business Cloud API JSON Payload (with Interactive Quick Reply Buttons)
    whatsapp_cloud_api_payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_digits,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": "🚨 URGENT BLOOD REQUIREMENT"
            },
            "body": {
                "text": (
                    f"Hospital: {req.hospital_name}\n"
                    f"Blood Group: {req.blood_group.value} ({req.component.value})\n"
                    f"Units Needed: {req.units} | Compatible: {compatible_groups_str}\n"
                    f"Contact: {req.contact_name} ({req.contact_phone})\n\n"
                    "Tap below to accept and coordinate donation directly."
                )
            },
            "footer": {
                "text": "Verified via NammaRaktha Bengaluru"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "btn_confirm_donate",
                            "title": "✅ Confirm & Donate"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "btn_hospital_map",
                            "title": "📍 Hospital Location"
                        }
                    }
                ]
            }
        }
    }

    return SOSMessage(
        english_text=english_text,
        kannada_text=kannada_text,
        kannada_phonetic=kannada_phonetic,
        whatsapp_share_url=whatsapp_share_url,
        twitter_share_url=twitter_share_url,
        twitter_text=twitter_text,
        donor_accept_url=clean_accept_url,
        hospital_maps_url=clean_map_url,
        verification_checklist=verification_checklist,
        whatsapp_cloud_api_payload=whatsapp_cloud_api_payload
    )

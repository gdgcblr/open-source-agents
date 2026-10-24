import re
from urllib.parse import urlparse, parse_qs

def decode_upi_qr(qr_payload: str) -> dict:
    """Decodes a UPI QR string (upi://pay?...) into structured payment details."""
    if "upi://pay" not in qr_payload.lower():
        return {"is_upi_qr": False, "raw_text": qr_payload}
    
    upi_match = re.search(r"(upi://pay\S+)", qr_payload, re.IGNORECASE)
    upi_uri = upi_match.group(1) if upi_match else qr_payload
    parsed = urlparse(upi_uri)
    params = parse_qs(parsed.query)
    
    payee_vpa = params.get("pa", ["Unknown VPA"])[0]
    payee_name = params.get("pn", ["Unknown Recipient"])[0]
    amount_str = params.get("am", ["0"])[0]
    
    try:
        amount_inr = float(amount_str.replace(",", ""))
    except ValueError:
        amount_inr = 0.0
        
    return {
        "is_upi_qr": True,
        "payee_vpa": payee_vpa,
        "payee_name": payee_name,
        "amount_inr": amount_inr,
        "consequence_summary": f"Requests immediate UPI payment of ₹{amount_inr:,.2f} to {payee_name} ({payee_vpa})."
    }

def extract_pricing_and_autopay(screen_text: str) -> dict:
    """Detects hidden auto-renewals, subscription traps, and UPI Autopay mandates in screen text."""
    amounts = re.findall(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", screen_text, re.IGNORECASE)
    numeric_amounts = [float(a.replace(",", "")) for a in amounts if a.replace(",", "").replace(".", "").isdigit()]
    
    lower_text = screen_text.lower()
    autopay_triggers = [
        kw for kw in ["auto-renew", "automatically renews", "autopay", "/year", "/month", "after 3 days", "recurring", "mandate"]
        if kw in lower_text
    ]
    
    return {
        "detected_amounts_inr": numeric_amounts,
        "immediate_charge_inr": min(numeric_amounts) if numeric_amounts else 0.0,
        "max_future_charge_inr": max(numeric_amounts) if numeric_amounts else 0.0,
        "is_recurring_autopay": len(autopay_triggers) > 0,
        "triggers": autopay_triggers
    }

def audit_app_permissions(app_purpose: str, screen_text: str) -> dict:
    """Audits whether permissions requested on screen are excessive for the app's stated purpose."""
    sensitive_map = {
        "CONTACTS": ["contact", "address book", "phonebook"],
        "LOCATION": ["location", "gps"],
        "SMS_MESSAGES": ["sms", "text message", "read messages", "otp"],
        "CALL_LOGS": ["call log", "call history"]
    }
    lower_text = screen_text.lower()
    flagged = [perm for perm, kws in sensitive_map.items() if any(k in lower_text for k in kws)]
    
    return {
        "app_purpose": app_purpose,
        "flagged_permissions": flagged,
        "is_overreaching": len(flagged) > 0
    }
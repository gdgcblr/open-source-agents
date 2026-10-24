import re

class PrivacyGuard:
    """Masks PII (Personally Identifiable Information) before sending data to LLMs."""
    
    # Basic patterns for common PII
    PATTERNS = {
        "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "phone": r"\+?\d{1,3}[-.\s]?\d{10}",
        "upi_id": r"[a-zA-Z0-9.\-_]{3,256}@[a-zA-Z]{2,32}",
    }

    @classmethod
    def scrub(cls, text: str) -> str:
        if not text:
            return text
        
        scrubbed = text
        for label, pattern in cls.PATTERNS.items():
            scrubbed = re.sub(pattern, f"[{label.upper()}_MASKED]", scrubbed)
        
        return scrubbed

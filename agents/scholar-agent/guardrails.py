import re
import unicodedata
# Additional security guardrails to prevent prompt injection attacks
"""
guardrails.py - Security and Adversarial Sanitization Layer
"""
import re
import unicodedata
from typing import Tuple, List


class SecurityGuardrails:
    """
    Defensive input sanitization layer against prompt injections and homoglyphs.
    """

    INJECTION_PATTERNS = [
        # 1. Goal hijacking and instruction overrides
        r"(?:ignore|disregard|forget|bypass)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|constraints|rules|prompt|directives)",
        r"disregard\s+(?:the\s+)?job\s+description",
        r"you\s+are\s+now\s+(?:an?\s+)?(?:evaluator|recruiter|admin|assistant|system)\s+who",
        
        # 2. System and admin spoofing (matches 'SYSTEM OVERRIDE', 'SYSTEM COMMAND', etc.)
        r"(?:system|admin|security)\s*(?:instruction|override|directive|command|prompt)",
        r"admin_override",
        r"\[(?:system|user|assistant|instruction|override)\]",
        r"role\s*:\s*(?:system|assistant)",
        
        # 3. Score tampering
        r"(?:give|grant|award|score|rate)\s+(?:this\s+)?(?:candidate|paper|cv|resume)?\s*(?:a\s+)?(?:perfect\s+)?(?:100(?:\.0)?(?:/100)?|maximum\s+score)",
        r"(?:override\s+final_score)"
    ]

    def __init__(self):
        self._compiled_regex = re.compile(
            "|".join(f"(?:{p})" for p in self.INJECTION_PATTERNS),
            flags=re.IGNORECASE | re.MULTILINE
        )

    def sanitize(self, text: str) -> str:
        """
        Normalizes Unicode (NFKC) and strips injection patterns.
        """
        if not text:
            return ""

        # Step 1: Normalize Unicode homoglyphs and remove non-printable characters
        normalized = unicodedata.normalize("NFKC", text)
        cleaned_chars = [
            ch for ch in normalized 
            if unicodedata.category(ch) not in ["Cf", "Cc"] or ch in ["\n", "\t", "\r"]
        ]
        sanitized = "".join(cleaned_chars)

        # Step 2: Redact injection patterns
        sanitized = self._compiled_regex.sub("[SECURITY_REDACTED]", sanitized)

        # Step 3: Collapse whitespace
        sanitized = re.sub(r"[ \t]+", " ", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

        return sanitized.strip()
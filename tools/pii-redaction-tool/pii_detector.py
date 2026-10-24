"""Core PII detection engine with regex + optional AI detection."""
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from config import settings


class PIICategory(Enum):
    """PII categories supported by the detector."""
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    US_SSN = "US_SSN"
    CREDIT_CARD = "CREDIT_CARD"
    IP_ADDRESS = "IP_ADDRESS"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    MEDICAL_LICENSE = "MEDICAL_LICENSE"
    PASSPORT = "PASSPORT"
    DRIVER_LICENSE = "DRIVER_LICENSE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    IBAN = "IBAN"


@dataclass
class PIIEntity:
    """Detected PII entity."""
    text: str
    category: str
    confidence: float
    start: int
    end: int
    detection_method: str  # "regex", "ner", "ai"


class PIIDetector:
    """PII detection engine using regex + optional AI."""

    def __init__(self):
        """Initialize the detector."""
        self._setup_custom_patterns()

    def _setup_custom_patterns(self):
        """Setup custom regex patterns for PII detection."""
        # Additional patterns can be added here
        pass

    def detect_pii(self, text: str) -> List[PIIEntity]:
        """
        Detect PII in text using regex + optional AI.

        Args:
            text: Input text to analyze

        Returns:
            List of detected PII entities
        """
        all_entities = []

        # Layer 1: Regex-based detection (fast, high precision)
        if settings.ENABLE_REGEX_DETECTION:
            regex_entities = self._detect_with_regex(text)
            all_entities.extend(regex_entities)

        # Layer 2: AI-based detection (slower, higher accuracy, optional)
        if settings.ENABLE_AI_DETECTION:
            ai_entities = self._detect_with_ai(text)
            all_entities.extend(ai_entities)

        # Filter by confidence threshold and deduplicate
        filtered_entities = self._filter_and_deduplicate(all_entities)

        return filtered_entities

    def _detect_with_regex(self, text: str) -> List[PIIEntity]:
        """Detect PII using regex patterns."""
        entities = []

        # Email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, text):
            entities.append(PIIEntity(
                text=match.group(),
                category=PIICategory.EMAIL_ADDRESS.value,
                confidence=0.95,
                start=match.start(),
                end=match.end(),
                detection_method="regex"
            ))

        # US SSN pattern
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        for match in re.finditer(ssn_pattern, text):
            entities.append(PIIEntity(
                text=match.group(),
                category=PIICategory.US_SSN.value,
                confidence=0.98,
                start=match.start(),
                end=match.end(),
                detection_method="regex"
            ))

        # Credit card pattern (Luhn algorithm validation would be better)
        cc_pattern = r'\b(?:\d[ -]*?){13,16}\b'
        for match in re.finditer(cc_pattern, text):
            entities.append(PIIEntity(
                text=match.group(),
                category=PIICategory.CREDIT_CARD.value,
                confidence=0.85,
                start=match.start(),
                end=match.end(),
                detection_method="regex"
            ))

        # IP address pattern
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        for match in re.finditer(ip_pattern, text):
            entities.append(PIIEntity(
                text=match.group(),
                category=PIICategory.IP_ADDRESS.value,
                confidence=0.90,
                start=match.start(),
                end=match.end(),
                detection_method="regex"
            ))

        # Phone number pattern (US)
        phone_pattern = r'\b(?:\+?1[-. ]?)?\(?[0-9]{3}\)?[-. ]?[0-9]{3}[-. ]?[0-9]{4}\b'
        for match in re.finditer(phone_pattern, text):
            entities.append(PIIEntity(
                text=match.group(),
                category=PIICategory.PHONE_NUMBER.value,
                confidence=0.88,
                start=match.start(),
                end=match.end(),
                detection_method="regex"
            ))

        return entities

    def _detect_with_ai(self, text: str) -> List[PIIEntity]:
        """Detect PII using local AI model (Ollama)."""
        entities = []

        try:
            import requests

            # Use Ollama's local API from settings
            ollama_url = settings.OLLAMA_URL
            ollama_model = settings.OLLAMA_MODEL

            prompt = f"""
            Analyze the following text and identify all Personally Identifiable Information (PII).
            Return ONLY a JSON object with this structure:
            {{
                "pii_entities": [
                    {{
                        "text": "the exact PII text",
                        "category": "EMAIL_ADDRESS|PHONE_NUMBER|US_SSN|CREDIT_CARD|PERSON|LOCATION|DATE_OF_BIRTH",
                        "confidence": 0.0-1.0,
                        "start": character_index,
                        "end": character_index
                    }}
                ]
            }}

            Text to analyze:
            {text[:2000]}
            """

            response = requests.post(ollama_url, json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }, timeout=30)

            if response.status_code == 200:
                result = response.json()
                # Parse AI response and convert to PIIEntity
                # This is a simplified version - in production, add proper JSON parsing
                # and error handling
                pass

        except Exception as e:
            print(f"AI detection error: {e}")

        return entities

    def _filter_and_deduplicate(self, entities: List[PIIEntity]) -> List[PIIEntity]:
        """Filter by confidence and remove duplicates."""
        # Filter by confidence threshold
        filtered = [e for e in entities if e.confidence >= settings.CONFIDENCE_THRESHOLD]

        # Deduplicate overlapping entities (keep highest confidence)
        filtered.sort(key=lambda x: (-x.confidence, x.start))
        deduplicated = []

        for entity in filtered:
            # Check for overlap with existing entities
            overlap = False
            for existing in deduplicated:
                if (entity.start < existing.end and entity.end > existing.start):
                    overlap = True
                    break

            if not overlap:
                deduplicated.append(entity)

        return deduplicated

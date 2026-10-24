"""Redaction engine with multiple strategies."""
import re
import hashlib
from typing import List, Dict, Optional
from enum import Enum

from pii_detector import PIIEntity, PIICategory
from config import settings


class RedactionStrategy(Enum):
    """Redaction strategies."""
    FULL = "full"  # Complete replacement
    PARTIAL = "partial"  # Show first/last N characters
    HASH = "hash"  # Replace with hash
    MASK = "mask"  # Pattern-based masking


class RedactionEngine:
    """Engine for redacting PII from text."""

    def __init__(self):
        """Initialize redaction engine."""
        self.strategy = settings.REDACTION_STRATEGY
        self.replacement_char = settings.REDACTION_CHAR
        self.partial_length = settings.PARTIAL_REDACTION_LENGTH

    def redact(
        self,
        text: str,
        entities: List[PIIEntity],
        strategy: Optional[str] = None
    ) -> str:
        """
        Redact PII entities from text.

        Args:
            text: Original text
            entities: List of PII entities to redact
            strategy: Override default strategy

        Returns:
            Redacted text
        """
        if not entities:
            return text

        # Sort entities by position (reverse order to preserve indices)
        sorted_entities = sorted(entities, key=lambda x: x.start, reverse=True)

        redacted_text = text
        for entity in sorted_entities:
            replacement = self._get_replacement(entity, strategy)
            redacted_text = (
                redacted_text[:entity.start] +
                replacement +
                redacted_text[entity.end:]
            )

        return redacted_text

    def _get_replacement(self, entity: PIIEntity, strategy: Optional[str] = None) -> str:
        """Get replacement text based on strategy."""
        strategy = strategy or self.strategy

        if strategy == RedactionStrategy.FULL.value:
            return self._full_redaction(entity)
        elif strategy == RedactionStrategy.PARTIAL.value:
            return self._partial_redaction(entity)
        elif strategy == RedactionStrategy.HASH.value:
            return self._hash_redaction(entity)
        elif strategy == RedactionStrategy.MASK.value:
            return self._mask_redaction(entity)
        else:
            return self._full_redaction(entity)

    def _full_redaction(self, entity: PIIEntity) -> str:
        """Full redaction - complete replacement."""
        return self.replacement_char

    def _partial_redaction(self, entity: PIIEntity) -> str:
        """Partial redaction - show first/last N characters."""
        text = entity.text
        length = len(text)

        if length <= self.partial_length * 2:
            # If text is too short, do full redaction
            return self.replacement_char

        # Show first N and last N characters
        visible_start = text[:self.partial_length]
        visible_end = text[-self.partial_length:]
        masked_middle = '*' * (length - 2 * self.partial_length)

        return f"{visible_start}{masked_middle}{visible_end}"

    def _hash_redaction(self, entity: PIIEntity) -> str:
        """Hash-based redaction - replace with hash."""
        hash_value = hashlib.sha256(entity.text.encode()).hexdigest()[:8]
        return f"[{entity.category.upper()}_HASH:{hash_value}]"

    def _mask_redaction(self, entity: PIIEntity) -> str:
        """Pattern-based masking - preserve format."""
        text = entity.text

        # Email masking
        if entity.category == PIICategory.EMAIL_ADDRESS.value:
            parts = text.split('@')
            if len(parts) == 2:
                username = parts[0]
                domain = parts[1]
                masked_username = username[:2] + '*' * (len(username) - 2)
                return f"{masked_username}@{domain}"

        # Phone masking
        if entity.category == PIICategory.PHONE_NUMBER.value:
            # Keep last 4 digits
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) >= 4:
                return '*' * (len(digits) - 4) + digits[-4:]

        # SSN masking (show last 4)
        if entity.category == PIICategory.US_SSN.value:
            parts = text.split('-')
            if len(parts) == 3:
                return f"***-**-{parts[2]}"

        # Credit card masking (show last 4)
        if entity.category == PIICategory.CREDIT_CARD.value:
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) >= 4:
                return '*' * (len(digits) - 4) + digits[-4:]

        # Default to full redaction
        return self.replacement_char


class ComplianceRedactor:
    """Compliance-aware redaction with regulatory requirements."""

    def __init__(self):
        """Initialize compliance redactor."""
        self.engine = RedactionEngine()
        self.compliance_mode = settings.COMPLIANCE_MODE

    def redact_with_compliance(
        self,
        text: str,
        entities: List[PIIEntity],
        strategy: Optional[str] = None
    ) -> Dict:
        """
        Redact with compliance-specific rules.

        Returns:
            Dict with redacted text and compliance report
        """
        # Filter entities based on compliance mode
        filtered_entities = self._filter_by_compliance(entities)

        # Apply redaction
        redacted_text = self.engine.redact(text, filtered_entities, strategy=strategy)

        # Generate compliance report
        report = self._generate_compliance_report(
            text,
            redacted_text,
            filtered_entities
        )

        return {
            "redacted_text": redacted_text,
            "compliance_report": report,
            "entities_redacted": len(filtered_entities),
            "compliance_mode": self.compliance_mode
        }

    def _filter_by_compliance(self, entities: List[PIIEntity]) -> List[PIIEntity]:
        """Filter entities based on compliance mode requirements."""
        if self.compliance_mode == "STRICT":
            # Redact all detected PII
            return entities

        elif self.compliance_mode == "GDPR":
            # GDPR focuses on: names, emails, phone, IDs, location
            gdpr_categories = [
                PIICategory.PERSON.value,
                PIICategory.EMAIL_ADDRESS.value,
                PIICategory.PHONE_NUMBER.value,
                PIICategory.LOCATION.value,
                PIICategory.DATE_OF_BIRTH.value,
                PIICategory.PASSPORT.value,
                PIICategory.DRIVER_LICENSE.value
            ]
            return [e for e in entities if e.category in gdpr_categories]

        elif self.compliance_mode == "CCPA":
            # CCPA focuses on: names, emails, phone, addresses
            ccpa_categories = [
                PIICategory.PERSON.value,
                PIICategory.EMAIL_ADDRESS.value,
                PIICategory.PHONE_NUMBER.value,
                PIICategory.LOCATION.value
            ]
            return [e for e in entities if e.category in ccpa_categories]

        elif self.compliance_mode == "HIPAA":
            # HIPAA focuses on: names, dates, contact info, medical IDs
            hipaa_categories = [
                PIICategory.PERSON.value,
                PIICategory.EMAIL_ADDRESS.value,
                PIICategory.PHONE_NUMBER.value,
                PIICategory.DATE_OF_BIRTH.value,
                PIICategory.MEDICAL_LICENSE.value
            ]
            return [e for e in entities if e.category in hipaa_categories]

        return entities

    def _generate_compliance_report(
        self,
        original: str,
        redacted: str,
        entities: List[PIIEntity]
    ) -> Dict:
        """Generate compliance report."""
        # Count by category
        category_counts = {}
        for entity in entities:
            category_counts[entity.category] = category_counts.get(entity.category, 0) + 1

        # Calculate redaction percentage
        original_size = len(original)
        redacted_size = len(redacted)
        redaction_percentage = ((original_size - redacted_size) / original_size * 100) if original_size > 0 else 0

        return {
            "compliance_standard": self.compliance_mode,
            "categories_redacted": category_counts,
            "total_entities_redacted": len(entities),
            "original_text_size": original_size,
            "redacted_text_size": redacted_size,
            "redaction_percentage": round(redaction_percentage, 2),
            "redaction_strategy": self.engine.strategy,
            "timestamp": self._get_timestamp()
        }

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()

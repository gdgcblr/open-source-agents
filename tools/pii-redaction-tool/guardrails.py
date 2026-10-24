"""Guardrails system for PII Redaction Agent."""
import time
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
from pathlib import Path

from ratelimit import limits, sleep_and_retry
from cryptography.fernet import Fernet

from config import settings


@dataclass
class AuditLogEntry:
    """Audit log entry for security compliance."""
    timestamp: str
    action: str
    input_hash: str
    input_size: int
    pii_count: int
    pii_categories: List[str]
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "success"
    error_message: Optional[str] = None


class InputValidator:
    """Validates input against security constraints."""

    @staticmethod
    def validate_input_size(text: str) -> bool:
        """Validate input size is within limits."""
        size = len(text.encode('utf-8'))
        if size > settings.MAX_INPUT_SIZE:
            raise ValueError(
                f"Input size ({size} bytes) exceeds maximum allowed "
                f"({settings.MAX_INPUT_SIZE} bytes)"
            )
        return True

    @staticmethod
    def validate_text_encoding(text: str) -> bool:
        """Validate text is properly encoded."""
        try:
            text.encode('utf-8')
            return True
        except UnicodeEncodeError:
            raise ValueError("Input contains invalid UTF-8 characters")

    @staticmethod
    def validate_content_type(text: str) -> bool:
        """Validate content is text-based."""
        if not isinstance(text, str):
            raise ValueError("Input must be a string")
        return True


class RateLimiter:
    """Rate limiting to prevent abuse."""

    def __init__(self):
        """Initialize rate limiter."""
        self.requests: Dict[str, List[float]] = defaultdict(list)

    @sleep_and_retry
    @limits(calls=settings.RATE_LIMIT_REQUESTS, period=settings.RATE_LIMIT_PERIOD)
    def check_rate_limit(self, identifier: str = "default") -> bool:
        """Check if request is within rate limits."""
        return True

    def is_allowed(self, identifier: str = "default") -> bool:
        """Check if request is allowed based on rate limits."""
        now = time.time()
        # Clean old requests
        self.requests[identifier] = [
            t for t in self.requests[identifier]
            if now - t < settings.RATE_LIMIT_PERIOD
        ]

        if len(self.requests[identifier]) >= settings.RATE_LIMIT_REQUESTS:
            return False

        self.requests[identifier].append(now)
        return True


class AuditLogger:
    """Audit logging for compliance and security."""

    def __init__(self):
        """Initialize audit logger."""
        self.log_path = Path(settings.AUDIT_LOG_PATH)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: AuditLogEntry) -> None:
        """Write audit log entry."""
        if not settings.ENABLE_AUDIT_LOGGING:
            return

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(entry)) + '\n')

    def log_detection(
        self,
        text: str,
        pii_entities: List,
        action: str = "detect",
        status: str = "success",
        error: Optional[str] = None
    ) -> None:
        """Log a PII detection event."""
        input_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        categories = list(set([e.category for e in pii_entities]))

        entry = AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action=action,
            input_hash=input_hash,
            input_size=len(text.encode('utf-8')),
            pii_count=len(pii_entities),
            pii_categories=categories,
            status=status,
            error_message=error
        )

        self.log(entry)

    def get_recent_logs(self, limit: int = 100) -> List[AuditLogEntry]:
        """Retrieve recent audit logs."""
        if not self.log_path.exists():
            return []

        entries = []
        with open(self.log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    entries.append(AuditLogEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue

        return entries[-limit:]


class ConfidenceFilter:
    """Filters PII entities based on confidence thresholds."""

    @staticmethod
    def filter_by_confidence(
        entities: List,
        threshold: float = None
    ) -> List:
        """Filter entities by confidence threshold."""
        if threshold is None:
            threshold = settings.CONFIDENCE_THRESHOLD

        return [e for e in entities if e.confidence >= threshold]

    @staticmethod
    def apply_category_weights(
        entities: List,
        category_weights: Dict[str, float]
    ) -> List:
        """Apply category-specific confidence adjustments."""
        weighted_entities = []
        for entity in entities:
            weight = category_weights.get(entity.category, 1.0)
            adjusted_confidence = entity.confidence * weight
            if adjusted_confidence >= settings.CONFIDENCE_THRESHOLD:
                weighted_entities.append(entity)

        return weighted_entities


class SecurityGuardrails:
    """Main guardrails coordinator."""

    def __init__(self):
        """Initialize all guardrails components."""
        self.validator = InputValidator()
        self.rate_limiter = RateLimiter()
        self.audit_logger = AuditLogger()
        self.confidence_filter = ConfidenceFilter()

    def validate_request(
        self,
        text: str,
        identifier: str = "default"
    ) -> bool:
        """
        Validate a request against all guardrails.

        Returns:
            True if request passes all guardrails
        """
        # Input validation
        self.validator.validate_content_type(text)
        self.validator.validate_text_encoding(text)
        self.validator.validate_input_size(text)

        # Rate limiting
        if not self.rate_limiter.is_allowed(identifier):
            raise PermissionError(
                f"Rate limit exceeded: {settings.RATE_LIMIT_REQUESTS} "
                f"requests per {settings.RATE_LIMIT_PERIOD} seconds"
            )

        return True

    def log_detection(
        self,
        text: str,
        pii_entities: List,
        status: str = "success",
        error: Optional[str] = None
    ) -> None:
        """Log detection event."""
        self.audit_logger.log_detection(
            text=text,
            pii_entities=pii_entities,
            action="detect",
            status=status,
            error=error
        )

    def filter_entities(self, entities: List) -> List:
        """Apply confidence filtering to entities."""
        return self.confidence_filter.filter_by_confidence(entities)

    def get_audit_trail(self, limit: int = 100) -> List[AuditLogEntry]:
        """Retrieve audit trail."""
        return self.audit_logger.get_recent_logs(limit)

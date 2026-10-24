"""Streaming support for large files."""
import asyncio
from typing import AsyncIterator, Optional
from pathlib import Path

from pii_detector import PIIDetector
from redaction_engine import ComplianceRedactor
from guardrails import SecurityGuardrails


class StreamingPIIRedactor:
    """Streaming PII redaction for large files."""

    def __init__(self, chunk_size: int = 8192):
        """Initialize streaming redactor."""
        self.chunk_size = chunk_size
        self.detector = PIIDetector()
        self.redactor = ComplianceRedactor()
        self.guardrails = SecurityGuardrails()

    async def redact_file_stream(
        self,
        input_path: str,
        output_path: str,
        strategy: Optional[str] = None,
        compliance_mode: Optional[str] = None
    ) -> AsyncIterator[dict]:
        """
        Redact PII from a file in streaming fashion.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            strategy: Redaction strategy
            compliance_mode: Compliance mode

        Yields:
            Progress updates
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        total_size = input_file.stat().st_size
        processed = 0

        with open(input_file, 'r', encoding='utf-8') as infile, \
             open(output_file, 'w', encoding='utf-8') as outfile:

            for line in infile:
                # Process each line
                self.guardrails.validate_request(line)
                entities = self.detector.detect_pii(line)
                filtered = self.guardrails.filter_entities(entities)

                if compliance_mode:
                    self.redactor.compliance_mode = compliance_mode

                redacted = self.redactor.redact_with_compliance(
                    line,
                    filtered,
                    strategy=strategy
                )

                outfile.write(redacted["redacted_text"])

                processed += len(line.encode('utf-8'))
                progress = (processed / total_size) * 100

                yield {
                    "progress": progress,
                    "processed_bytes": processed,
                    "total_bytes": total_size,
                    "entities_redacted": len(filtered)
                }

    async def redact_text_stream(
        self,
        text: str,
        strategy: Optional[str] = None,
        compliance_mode: Optional[str] = None
    ) -> AsyncIterator[dict]:
        """
        Redact PII from text in streaming fashion (chunk by chunk).

        Args:
            text: Input text
            strategy: Redaction strategy
            compliance_mode: Compliance mode

        Yields:
            Progress updates
        """
        chunk_size = 1000  # Process 1000 characters at a time
        total_length = len(text)
        processed = 0
        redacted_text = ""

        for i in range(0, total_length, chunk_size):
            chunk = text[i:i + chunk_size]

            self.guardrails.validate_request(chunk)
            entities = self.detector.detect_pii(chunk)
            filtered = self.guardrails.filter_entities(entities)

            if compliance_mode:
                self.redactor.compliance_mode = compliance_mode

            result = self.redactor.redact_with_compliance(
                chunk,
                filtered,
                strategy=strategy
            )

            redacted_text += result["redacted_text"]
            processed = min(i + chunk_size, total_length)
            progress = (processed / total_length) * 100

            yield {
                "progress": progress,
                "processed_chars": processed,
                "total_chars": total_length,
                "entities_redacted": len(filtered),
                "redacted_chunk": result["redacted_text"]
            }

        yield {
            "progress": 100,
            "processed_chars": total_length,
            "total_chars": total_length,
            "entities_redacted": 0,
            "redacted_text": redacted_text
        }

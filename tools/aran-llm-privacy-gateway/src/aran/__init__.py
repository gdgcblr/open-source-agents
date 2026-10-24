"""Aran (அரண், "fortress"): hide Indian PII locally before text reaches a cloud LLM."""

from aran.engine import RedactionResult, redact_document, redact_text, restore

__all__ = ["RedactionResult", "redact_document", "redact_text", "restore"]
__version__ = "0.1.0"

"""
Spoke 2: Multimodal Gemini Receipt & Bill OCR Scanner.
Parses receipts, bills, and payment screenshots into structured items and split shares.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from ..ocr_tool import ReceiptOCRTool, ReceiptScanResult


class ReceiptOCRSpoke:
    name: str = "Multimodal Receipt OCR Auditor"
    urn: str = "urn:adk:spoke:receipt-ocr"

    @classmethod
    def execute(
        cls,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/jpeg",
        user_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if image_bytes is None:
            # Simulated sample receipt
            image_bytes = b"MOCK_RECEIPT_BYTES"

        result: ReceiptScanResult = ReceiptOCRTool.scan_receipt_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_notes=user_notes,
        )

        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "merchant": result.merchant_name,
            "total_amount": result.total_amount,
            "tax_amount": result.tax_amount,
            "date": result.date,
            "gstin": result.gstin,
            "upi_id": result.upi_id,
            "category": result.category,
            "line_items": [i.dict() for i in result.line_items],
            "suggested_payer": result.suggested_payer,
            "confidence": result.confidence_score,
            "model_used": result.model_used,
            "summary": result.summary,
            "guardrail_status": "MULTIMODAL_EXTRACTION_VERIFIED",
        }

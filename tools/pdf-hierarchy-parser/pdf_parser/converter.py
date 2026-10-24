"""Docling-backed PDF conversion into a flat, framework-neutral item list."""

from __future__ import annotations

import os
from typing import Any


def _label_value(label: Any) -> str:
    """Normalize Docling's label enum/string into a plain lowercase string."""
    value = getattr(label, "value", label)
    return str(value).lower() if value is not None else ""


def convert_pdf(pdf_path: str, do_ocr: bool = False) -> list[dict]:
    """Convert a PDF into a flat list of normalized item dicts.

    Docling objects never leave this module: callers receive plain dicts that
    are trivial to serialize, mock, or feed into the graph builder.

    Args:
        pdf_path: Path to a PDF file on disk.
        do_ocr: Enable OCR for scanned/image-only PDFs. Off by default for
            speed on digital PDFs.

    Returns:
        A list of ``{"class", "label", "text", "index"}`` dicts in reading order.

    Raises:
        FileNotFoundError: If ``pdf_path`` does not exist.
        RuntimeError: If Docling is not installed.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Docling is not installed. Run: pip install -r requirements.txt"
        ) from exc

    pipeline_options = PdfPipelineOptions(do_ocr=do_ocr)
    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
    )

    result = converter.convert(pdf_path)
    items: list[dict] = []
    for index, (item, _docling_level) in enumerate(result.document.iterate_items()):
        items.append(
            {
                "class": type(item).__name__,
                "label": _label_value(getattr(item, "label", "")),
                "text": getattr(item, "text", "") or "",
                "index": index,
            }
        )
    return items

"""Turn any supported document into text (or a table) locally."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from aran import local_llm

TEXT_EXT = {".txt", ".md", ".json", ".log", ".eml"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
TABLE_EXT = {".csv", ".xlsx", ".xls"}
PDF_EXT = {".pdf"}
SUPPORTED = TEXT_EXT | IMAGE_EXT | TABLE_EXT | PDF_EXT


@dataclass
class Document:
    kind: str  # text | pdf | scanned_pdf | image | table
    text: str = ""
    table: pd.DataFrame | None = None


def read(path: Path) -> Document:
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return Document("text", path.read_text(errors="replace"))
    if ext in IMAGE_EXT:
        return Document("image", local_llm.transcribe_image(path))
    if ext in TABLE_EXT:
        df = pd.read_csv(path, dtype=str) if ext == ".csv" else pd.read_excel(path, dtype=str)
        return Document("table", table=df.fillna(""))
    if ext in PDF_EXT:
        return _read_pdf(path)
    raise ValueError(f"Unsupported file type {ext!r}. Supported: {', '.join(sorted(SUPPORTED))}")


def _read_pdf(path: Path) -> Document:
    pages, scanned = [], False
    for page in PdfReader(path).pages:
        text = (page.extract_text() or "").strip()
        if len(text) < 20 and page.images:
            # No text layer: a scanned page. OCR its images with the local vision model.
            scanned = True
            text = "\n".join(local_llm.transcribe_image(img.data) for img in page.images)
        pages.append(text)
    return Document("scanned_pdf" if scanned else "pdf", "\n\n".join(pages))

from __future__ import annotations

from pathlib import Path

import pymupdf

from pdf_to_surveyjs_agent.tools import extract_pdf, extract_pdf_text


def _write_pdf(path: Path, text: str | None = None) -> None:
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_extracts_text_and_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "form.pdf"
    _write_pdf(pdf_path, "Full name: __________________ Required")

    result = extract_pdf(pdf_path)

    assert result.ok is True
    assert result.page_count == 1
    assert "Full name" in result.text
    assert result.character_count == len(result.text)
    assert result.warnings == []


def test_reports_scanned_or_empty_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    _write_pdf(pdf_path)

    result = extract_pdf(pdf_path)

    assert result.ok is True
    assert result.text == ""
    assert "OCR is not included" in result.warnings[0]


def test_rejects_non_pdf_extension(tmp_path: Path) -> None:
    text_path = tmp_path / "form.txt"
    text_path.write_text("not a PDF", encoding="utf-8")

    result = extract_pdf(text_path)

    assert result.ok is False
    assert result.error == "Only .pdf files are supported."


def test_rejects_fake_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "form.pdf"
    pdf_path.write_bytes(b"This is not a PDF")

    result = extract_pdf(pdf_path)

    assert result.ok is False
    assert "valid PDF signature" in (result.error or "")


def test_missing_file_has_clear_error(tmp_path: Path) -> None:
    result = extract_pdf(tmp_path / "missing.pdf")

    assert result.ok is False
    assert "does not exist" in (result.error or "")


def test_adk_tool_rejects_path_outside_allowed_root(
    tmp_path: Path, monkeypatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside_pdf = tmp_path / "outside.pdf"
    _write_pdf(outside_pdf, "A form outside the approved directory")
    monkeypatch.setenv("PDF_SURVEY_ALLOWED_ROOT", str(allowed))

    result = extract_pdf_text(str(outside_pdf))

    assert result["ok"] is False
    assert "may only read PDFs inside" in result["error"]


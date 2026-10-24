"""Draw the fictional visit PDFs from app.corpus."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.corpus import BAIT, VISITS
from app.paths import FIXTURES


def visit_lines(visit: dict) -> list[str]:
    lines = [
        "Fictional lab report",
        f"Patient name: {BAIT['name']}",
        f"Phone: {BAIT['phone']}",
        f"Email: {BAIT['email']}",
        f"Record ID: {BAIT['record_id']}",
        f"Collected: {visit['collected_on']}",
        f"Panel: {visit['panel']}",
        "",
        "RESULTS",
        "Test | Result | Unit | Reference interval | Flag",
    ]
    for name, value, unit, ref, flag in visit["rows"]:
        lines.append(f"{name} | {value} | {unit} | {ref} | {flag}")
    lines.append("")
    lines.append("Reference intervals are the ones printed on this fictional report.")
    return lines


def write_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setTitle("Fictional lab report")
    pdf.setFont("Helvetica", 11)
    y = 750
    for line in lines:
        pdf.drawString(54, y, line)
        y -= 18
        if y < 54:
            pdf.showPage()
            pdf.setFont("Helvetica", 11)
            y = 750
    pdf.save()


def write_fixtures(directory: Path | None = None) -> list[Path]:
    target = directory or FIXTURES
    written: list[Path] = []
    for visit in VISITS:
        path = target / visit["file"]
        write_pdf(path, visit_lines(visit))
        written.append(path)
    return written


if __name__ == "__main__":
    for path in write_fixtures():
        print(path)

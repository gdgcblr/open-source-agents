import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

from .sbom import build_cyclonedx

FORMATS = ("pdf", "csv")
MAX_PDF_COMPONENTS = 40
CHARACTER_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "•": "-", "…": "...", " ": " ",
}
CSV_COLUMNS = ("generated_utc", "project", "rules", "section", "check", "status", "detail")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def project_name(project_path: str, explicit: str | None) -> str:
    if explicit:
        return slugify(explicit)
    readme = Path(project_path) / "README.md"
    if readme.is_file():
        for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                return slugify(line[2:])
    return "project"


def timestamp_now() -> datetime:
    return datetime.now(timezone.utc)


def base_filename(data: dict) -> str:
    stamp = data["generated"].strftime("%Y%m%d-%H%M%S")
    return f"preflight_{slugify(data['project'])}_{slugify(data['rules'])}_{stamp}"


def sbom_filename(data: dict) -> str:
    return f"{base_filename(data)}_sbom.cdx.json"


def clean_text(text: str) -> str:
    for source, target in CHARACTER_MAP.items():
        text = text.replace(source, target)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^\s*\*\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"\*(\S(?:[^*\n]*\S)?)\*", r"\1", text)
    return text.encode("latin-1", "replace").decode("latin-1")


def review_items(review: str) -> list[str]:
    items = []
    for line in review.splitlines():
        stripped = clean_text(line).strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def ecosystem_summary(components: list[dict]) -> str:
    counts: dict[str, int] = {}
    for component in components:
        counts[component["ecosystem"]] = counts.get(component["ecosystem"], 0) + 1
    return ", ".join(f"{count} {name}" for name, count in sorted(counts.items())) or "none"


def vuln_scan_note(posture: dict) -> str:
    state = posture.get("vuln_scan", "skipped")
    if state == "done":
        return f"done: {len(posture['vulnerabilities'])} known vulnerabilities found (OSV.dev)"
    if state == "failed":
        return "failed: lookup could not complete"
    return "skipped (enable with --vuln-scan; sends package names and versions to OSV.dev)"


def csv_rows(data: dict) -> list[list[str]]:
    generated = data["generated"].strftime("%Y-%m-%dT%H:%M:%SZ")
    head = [generated, data["project"], data["rules"]]
    rows = []
    for check in ("structure", "security"):
        result = data[check]
        if result["findings"]:
            for finding in result["findings"]:
                rows.append(head + ["pr_preflight", check, "FAIL", finding])
        else:
            rows.append(head + ["pr_preflight", check, result["status"].upper(), "No issues found."])
    if data.get("docs_review") is not None:
        items = review_items(data["docs_review"]) or [clean_text(data["docs_review"]).strip() or "No review produced."]
        for item in items:
            rows.append(head + ["pr_preflight", "docs_review", "SUGGESTION", item])
    posture = data.get("posture")
    if posture:
        components = posture["components"]
        rows.append(head + ["aspm", "sbom", "INFO", f"{len(components)} components ({ecosystem_summary(components)}); file: {sbom_filename(data)}"])
        if posture["findings"]:
            for finding in posture["findings"]:
                rows.append(head + ["aspm", "posture", finding["severity"].upper(), finding["message"]])
        else:
            rows.append(head + ["aspm", "posture", "PASS", "No posture issues found."])
        rows.append(head + ["aspm", "vulnerability_scan", "INFO", vuln_scan_note(posture)])
    rows.append(head + ["summary", "verdict", data["verdict"].upper(), "Decided by structure, security and high-severity ASPM findings."])
    return rows


def write_csv(data: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(csv_rows(data))


def write_pdf(data: dict, path: Path) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def line(text: str, size: int = 11, style: str = "", gap: float = 6) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, gap, clean_text(text), new_x="LMARGIN", new_y="NEXT")

    line("Contribution Preflight Report", 18, "B", 10)
    line(f"Project: {data['project']}")
    line(f"Rules: {data['rules']}")
    line(f"Generated (UTC): {data['generated'].strftime('%Y-%m-%d %H:%M:%S')}")
    line(f"Verdict: {data['verdict'].upper()}", 14, "B", 9)
    pdf.ln(3)

    line("Part 1 - PR Preflight", 15, "B", 9)
    for check in ("structure", "security"):
        result = data[check]
        line(f"{check.capitalize()}: {result['status'].upper()}", 13, "B", 8)
        if result["findings"]:
            for finding in result["findings"]:
                line(f"- {finding}")
        else:
            line("No issues found.")
        pdf.ln(2)
    if data.get("docs_review") is not None:
        line("Docs review (Gemma, suggestions only)", 13, "B", 8)
        items = review_items(data["docs_review"])
        for item in items or [data["docs_review"] or "No review produced."]:
            line(f"- {item}")
        pdf.ln(2)

    posture = data.get("posture")
    if posture:
        pdf.ln(2)
        line("Part 2 - ASPM and SBOM", 15, "B", 9)
        components = posture["components"]
        line(f"Posture: {posture['status'].upper()}", 13, "B", 8)
        if posture["findings"]:
            for finding in posture["findings"]:
                line(f"- [{finding['severity'].upper()}] {finding['message']}")
        else:
            line("No posture issues found.")
        pdf.ln(2)
        line(f"SBOM: {len(components)} components ({ecosystem_summary(components)})", 13, "B", 8)
        for component in components[:MAX_PDF_COMPONENTS]:
            version = component["version"] or f"unpinned ({component['spec']})"
            line(f"- {component['name']} {version} [{component['ecosystem']}]")
        if len(components) > MAX_PDF_COMPONENTS:
            line(f"... and {len(components) - MAX_PDF_COMPONENTS} more.")
        line(f"Full CycloneDX file: {sbom_filename(data)}", 10, "I", 5)
        pdf.ln(2)
        line(f"Vulnerability scan: {vuln_scan_note(posture)}", 11, "", 6)
        pdf.ln(2)

    line("The verdict comes from the structure, security and high-severity ASPM findings. The docs review is advisory.", 9, "I", 5)
    pdf.output(str(path))


def write_sbom(data: dict, path: Path) -> None:
    posture = data["posture"]
    bom = build_cyclonedx(data["project"], data["generated"], posture["components"], posture["vulnerabilities"])
    path.write_text(json.dumps(bom, indent=2), encoding="utf-8")


def write_reports(data: dict, out_dir: str, formats: tuple[str, ...]) -> list[Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    base = base_filename(data)
    written = []
    if "csv" in formats:
        path = target / f"{base}.csv"
        write_csv(data, path)
        written.append(path)
    if "pdf" in formats:
        path = target / f"{base}.pdf"
        write_pdf(data, path)
        written.append(path)
    if data.get("posture"):
        path = target / sbom_filename(data)
        write_sbom(data, path)
        written.append(path)
    return written

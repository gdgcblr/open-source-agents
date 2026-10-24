import csv
from datetime import datetime, timezone

from preflight.reporting import (
    base_filename,
    clean_text,
    project_name,
    review_items,
    slugify,
    write_reports,
)


def sample(**overrides) -> dict:
    data = {
        "project": "demo-app",
        "rules": "gdgcblr",
        "generated": datetime(2026, 10, 24, 13, 5, 9, tzinfo=timezone.utc),
        "verdict": "fail",
        "structure": {"status": "fail", "findings": ["Missing required file: .gitignore"]},
        "security": {"status": "pass", "findings": []},
        "docs_review": "Intro line\n* **Clarity:** The “summary” is vague.\n* Add usage — examples.",
    }
    data.update(overrides)
    return data


def test_slugify():
    assert slugify("Contribution Preflight Agent!") == "contribution-preflight-agent"
    assert slugify("???") == "project"
    assert slugify(".preflight.json") == "preflight-json"


def test_filename_has_name_rules_and_timestamp():
    assert base_filename(sample()) == "preflight_demo-app_gdgcblr_20261024-130509"


def test_project_name_precedence(tmp_path):
    (tmp_path / "README.md").write_text("# My Cool Tool\n")
    assert project_name(str(tmp_path), "Explicit Name") == "explicit-name"
    assert project_name(str(tmp_path), None) == "my-cool-tool"
    assert project_name(str(tmp_path / "missing"), None) == "project"


def test_clean_text_strips_markdown_and_unicode():
    cleaned = clean_text("**Bold** “quoted” — done ☃")
    assert "**" not in cleaned
    assert "“" not in cleaned and "—" not in cleaned
    cleaned.encode("latin-1")


def test_clean_text_strips_single_asterisk_emphasis():
    assert clean_text("the *specific* problem, 2 * 3") == "the specific problem, 2 * 3"


def test_review_items_extracts_bullets():
    items = review_items(sample()["docs_review"])
    assert items == ['Clarity: The "summary" is vague.', "Add usage - examples."]


def test_write_reports_creates_both_files(tmp_path):
    out = tmp_path / "reports"
    written = write_reports(sample(), str(out), ("csv", "pdf"))
    names = sorted(path.name for path in written)
    assert names == [
        "preflight_demo-app_gdgcblr_20261024-130509.csv",
        "preflight_demo-app_gdgcblr_20261024-130509.pdf",
    ]
    pdf = out / names[1]
    assert pdf.read_bytes().startswith(b"%PDF")


def test_csv_content(tmp_path):
    written = write_reports(sample(), str(tmp_path), ("csv",))
    with written[0].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["generated_utc", "project", "rules", "section", "check", "status", "detail"]
    checks = [(row[4], row[5]) for row in rows[1:]]
    assert ("structure", "FAIL") in checks
    assert ("security", "PASS") in checks
    assert checks.count(("docs_review", "SUGGESTION")) == 2
    assert checks[-1] == ("verdict", "FAIL")
    assert rows[1][0] == "2026-10-24T13:05:09Z"


def test_no_docs_rows_when_review_skipped(tmp_path):
    written = write_reports(sample(docs_review=None), str(tmp_path), ("csv",))
    with written[0].open(encoding="utf-8", newline="") as handle:
        checks = [row[4] for row in csv.reader(handle)]
    assert "docs_review" not in checks


def test_single_format_only(tmp_path):
    written = write_reports(sample(), str(tmp_path), ("pdf",))
    assert [path.suffix for path in written] == [".pdf"]


def test_empty_review_still_reported(tmp_path):
    written = write_reports(sample(docs_review=""), str(tmp_path), ("csv", "pdf"))
    assert len(written) == 2


def posture_sample() -> dict:
    component = {
        "name": "requests", "version": "2.32.3", "ecosystem": "PyPI", "source": "requirements.txt",
        "pinned": True, "spec": "==2.32.3", "scope": "required", "purl": "pkg:pypi/requests@2.32.3",
    }
    loose = dict(component, name="flask", version="", pinned=False, spec=">=3", purl="pkg:pypi/flask")
    return {
        "status": "fail",
        "components": [component, loose],
        "findings": [
            {"severity": "warn", "message": "Dependency not pinned to an exact version: flask"},
            {"severity": "high", "message": "Known vulnerability GHSA-demo in requests 2.32.3."},
        ],
        "vulnerabilities": [{"id": "GHSA-demo", "ref": "pkg:pypi/requests@2.32.3"}],
        "vuln_scan": "done",
    }


def test_csv_has_both_sections_with_posture(tmp_path):
    written = write_reports(sample(posture=posture_sample()), str(tmp_path), ("csv",))
    csv_path = next(path for path in written if path.suffix == ".csv")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))[1:]
    sections = {row[3] for row in rows}
    assert sections == {"pr_preflight", "aspm", "summary"}
    aspm = [(row[4], row[5]) for row in rows if row[3] == "aspm"]
    assert ("sbom", "INFO") in aspm
    assert ("posture", "WARN") in aspm
    assert ("posture", "HIGH") in aspm
    assert ("vulnerability_scan", "INFO") in aspm


def test_sbom_file_written_and_valid(tmp_path):
    import json

    written = write_reports(sample(posture=posture_sample()), str(tmp_path), ("pdf",))
    sbom_path = next(path for path in written if path.name.endswith("_sbom.cdx.json"))
    bom = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    assert len(bom["components"]) == 2
    assert bom["vulnerabilities"][0]["id"] == "GHSA-demo"


def test_no_sbom_when_aspm_disabled(tmp_path):
    written = write_reports(sample(), str(tmp_path), ("csv", "pdf"))
    assert not any(path.name.endswith("_sbom.cdx.json") for path in written)


def test_pdf_with_posture_is_valid(tmp_path):
    written = write_reports(sample(posture=posture_sample()), str(tmp_path), ("pdf",))
    pdf_path = next(path for path in written if path.suffix == ".pdf")
    assert pdf_path.read_bytes().startswith(b"%PDF")

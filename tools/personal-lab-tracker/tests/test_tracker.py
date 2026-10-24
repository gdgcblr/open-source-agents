"""Extraction, privacy, accounts, and the local dashboard."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.corpus import BAIT, VISITS
from app.extract import extract_pdf, text_is_unsafe
from app.facts import build_prompt
from app.main import Settings, create_app
from app.pdfgen import write_fixtures

BAIT_VALUES = list(BAIT.values())


@pytest.fixture()
def fixture_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "fixtures"
    write_fixtures(directory)
    return directory


@pytest.fixture()
def client(tmp_path: Path, fixture_dir: Path) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "labs.sqlite",
        secret="test-secret-not-used-outside-pytest",
        fixture_dir=fixture_dir,
        data_dir=tmp_path / "data",
    )
    app = create_app(settings)
    return TestClient(app)


def test_pdf_rows_drop_bait_identifiers(fixture_dir: Path) -> None:
    extraction = extract_pdf(fixture_dir / "visit-1.pdf")
    assert extraction.collected_on == "2025-11-02"
    assert extraction.panel_name == "Complete blood count"
    assert [row.display_name for row in extraction.rows] == [
        "Hemoglobin",
        "WBC",
        "Platelet count",
    ]
    assert extraction.rows[0].flag == "below"
    assert extraction.rows[0].value == pytest.approx(12.4)
    blob = extraction.redacted_text + " ".join(
        row.display_name + row.value_text for row in extraction.rows
    )
    for bait in BAIT_VALUES:
        assert bait not in blob
    assert "name" in extraction.removed
    assert "email" in extraction.removed


def _seed(db_path: Path, fixture_dir: Path) -> None:
    from app.auth import hash_password
    from app.db import create_user, init_db, insert_report

    init_db(db_path)
    user_id = create_user(db_path, "ada@example.com", hash_password("local-pass-1"))
    for visit in VISITS:
        extraction = extract_pdf(fixture_dir / visit["file"])
        insert_report(
            db_path,
            user_id,
            extraction.collected_on,
            extraction.panel_name,
            visit["file"],
            f"uploads/{user_id}/{visit['file']}",
            list(extraction.rows),
        )


def test_prompt_uses_only_lab_fields(fixture_dir: Path) -> None:
    from app.db import results_for_user

    db_path = fixture_dir.parent / "prompt.sqlite"
    _seed(db_path, fixture_dir)
    stored = results_for_user(db_path, 1)
    prompt = build_prompt(stored)
    assert "FACT_SHEET" in prompt
    assert "hemoglobin" in prompt
    assert "ldl cholesterol" in prompt
    assert '"flag": "below"' in prompt or '"flag": "above"' in prompt
    for bait in BAIT_VALUES:
        assert bait not in prompt
    assert not text_is_unsafe(prompt)


def test_meters_place_the_latest_value_on_the_printed_interval(fixture_dir: Path) -> None:
    from app.db import results_for_user
    from app.facts import meters_for

    db_path = fixture_dir.parent / "meters.sqlite"
    _seed(db_path, fixture_dir)
    meters = {item.analyte: item for item in meters_for(results_for_user(db_path, 1))}
    hemoglobin = meters["hemoglobin"]
    assert hemoglobin.flag == "within"
    assert hemoglobin.delta == "+1.2"
    assert hemoglobin.has_interval
    assert hemoglobin.within_start < hemoglobin.marker < hemoglobin.within_end
    ldl = meters["ldl cholesterol"]
    assert ldl.flag == "above"
    assert ldl.marker > ldl.within_end
    hdl = meters["hdl cholesterol"]
    assert hdl.flag == "within"
    assert hdl.marker >= hdl.within_start


def test_fact_sheet_tracks_hemoglobin_and_ldl(fixture_dir: Path) -> None:
    from app.db import results_for_user
    from app.facts import changes_for, outside_latest

    db_path = fixture_dir.parent / "facts.sqlite"
    _seed(db_path, fixture_dir)
    stored = results_for_user(db_path, 1)
    by_analyte = {item.analyte: item for item in changes_for(stored)}
    assert by_analyte["hemoglobin"].delta == "+1.2"
    assert by_analyte["ldl cholesterol"].delta == "-4"
    outside = {item.analyte: item.flag for item in outside_latest(stored)}
    assert outside["ldl cholesterol"] == "above"
    assert "hemoglobin" not in outside


def _register(client: TestClient, email: str, password: str = "local-pass-1") -> None:
    page = client.get("/register")
    token = _csrf(page.text)
    response = client.post(
        "/register",
        data={"csrf": token, "email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _csrf(html: str) -> str:
    marker = 'name="csrf" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


def test_account_is_local_and_dashboard_starts_empty(client: TestClient) -> None:
    anonymous = client.get("/", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login"
    _register(client, "ada@example.com")
    home = client.get("/")
    assert home.status_code == 200
    assert "No reports yet" in home.text
    assert "ada@example.com" in home.text
    assert "Demo User" not in home.text


def test_demo_record_stays_inside_the_account(client: TestClient, fixture_dir: Path) -> None:
    _register(client, "ada@example.com")
    home = client.get("/")
    loaded = client.post("/demo", data={"csrf": _csrf(home.text)}, follow_redirects=False)
    assert loaded.status_code == 303
    page = client.get("/")
    assert "Lab history" in page.text
    assert "Latest results" in page.text
    assert 'role="meter"' in page.text
    assert "Hemoglobin" in page.text
    assert "+1.2" in page.text
    assert "above" in page.text
    assert "FACT_SHEET" not in page.text
    assert "More about these numbers" in page.text
    for bait in BAIT_VALUES:
        assert bait not in page.text
    client.post("/logout", data={"csrf": _csrf(page.text)})
    _register(client, "bea@example.com")
    other = client.get("/")
    assert "No reports yet" in other.text
    missing = client.get("/reports/1")
    assert missing.status_code == 404


def test_upload_review_hides_identifiers_until_save(client: TestClient, fixture_dir: Path) -> None:
    _register(client, "ada@example.com")
    pdf = (fixture_dir / "visit-1.pdf").read_bytes()
    page = client.get("/")
    response = client.post(
        "/upload",
        data={"csrf": _csrf(page.text)},
        files={"report": ("My Lab.PDF", pdf, "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/review"
    review = client.get("/review")
    assert "Hemoglobin" in review.text
    assert "12.4" in review.text
    assert "Removed before this table" in review.text
    for bait in BAIT_VALUES:
        assert bait not in review.text
    saved = client.post(
        "/review",
        data={
            "csrf": _csrf(review.text),
            "collected_on": "2025-11-02",
            "panel_name": "Complete blood count",
            "display_name_0": "Hemoglobin",
            "value_text_0": "12.8",
            "unit_0": "g/dL",
            "ref_text_0": "13.0-17.0",
            "display_name_1": "WBC",
            "value_text_1": "6.1",
            "unit_1": "10^3/uL",
            "ref_text_1": "4.0-11.0",
            "display_name_2": "Platelet count",
            "value_text_2": "210",
            "unit_2": "10^3/uL",
            "ref_text_2": "150-450",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    detail = client.get(saved.headers["location"])
    assert "12.8" in detail.text
    assert "below" in detail.text

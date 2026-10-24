"""Settings, model extraction, and grounded summaries."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.corpus import BAIT
from app.main import Settings, create_app
from app.pdfgen import write_pdf
from tests.test_tracker import _csrf, _register


def _app(tmp_path: Path, handler) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "labs.sqlite",
        secret="test-secret-not-used-outside-pytest",
        fixture_dir=tmp_path / "fixtures",
        data_dir=tmp_path / "data",
    )
    app = create_app(settings)
    app.state.llm_client_factory = lambda: httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    return TestClient(app)


def test_settings_store_the_key_without_showing_it(tmp_path: Path) -> None:
    client = _app(tmp_path, lambda request: httpx.Response(500))
    assert client.get("/settings", follow_redirects=False).status_code == 303
    _register(client, "ada@example.com")
    page = client.get("/settings")
    saved = client.post(
        "/settings",
        data={
            "csrf": _csrf(page.text),
            "local_base_url": "http://127.0.0.1:11434/v1",
            "openai_api_key": "sk-test-secret-value",
            "extraction_provider": "openai",
            "extraction_model": "gpt-4o-mini",
            "summary_provider": "local",
            "summary_model": "gemma3",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    again = client.get("/settings")
    assert "sk-test-secret-value" not in again.text
    assert "A key is saved" in again.text
    assert "gpt-4o-mini" in again.text
    assert "gemma3" in again.text
    client.post("/logout", data={"csrf": _csrf(again.text)})
    _register(client, "bea@example.com")
    other = client.get("/settings")
    assert "sk-test-secret-value" not in other.text
    assert "A key is saved" not in other.text
    assert 'id="summary_model"' in other.text
    assert 'name="summary_model" list="model-names" value=""' in other.text


def _model_rows() -> dict:
    return {
        "collected_on": "2026-01-02",
        "panel_name": "Note",
        "rows": [
            {
                "display_name": "Hemoglobin",
                "value": "11.1",
                "unit": "g/dL",
                "reference_interval": "13.0-17.0",
            }
        ],
    }


def _prose_pdf(path: Path) -> None:
    write_pdf(
        path,
        [
            f"Patient name: {BAIT['name']}",
            f"Email: {BAIT['email']}",
            f"Phone: {BAIT['phone']}",
            f"Record ID: {BAIT['record_id']}",
            "Collected: 2026-01-02",
            "Panel: Note",
            "Hemoglobin was about 11.1",
        ],
    )


def test_local_extraction_sends_the_report_text(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_model_rows())}}]},
        )

    client = _app(tmp_path, handler)
    _register(client, "ada@example.com")
    settings_page = client.get("/settings")
    client.post(
        "/settings",
        data={
            "csrf": _csrf(settings_page.text),
            "local_base_url": "http://127.0.0.1:11434/v1",
            "openai_api_key": "",
            "extraction_provider": "local",
            "extraction_model": "gemma3",
            "summary_provider": "local",
            "summary_model": "",
        },
    )
    pdf_path = tmp_path / "note.pdf"
    _prose_pdf(pdf_path)
    home = client.get("/")
    assert "local model server" in home.text
    uploaded = client.post(
        "/upload",
        data={"csrf": _csrf(home.text)},
        files={"report": ("note.pdf", pdf_path.read_bytes(), "application/pdf")},
        follow_redirects=False,
    )
    assert uploaded.status_code == 303
    assert uploaded.headers["location"] == "/review"
    review = client.get("/review")
    assert "11.1" in review.text
    assert "local model server" in review.text
    for bait in BAIT.values():
        assert bait not in review.text
        assert bait in seen["body"]
    assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert "Hemoglobin was about 11.1" in seen["body"]


def test_openai_extraction_reads_a_typed_table(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_model_rows())}}]},
        )

    client = _app(tmp_path, handler)
    _register(client, "ada@example.com")
    settings_page = client.get("/settings")
    client.post(
        "/settings",
        data={
            "csrf": _csrf(settings_page.text),
            "local_base_url": "http://127.0.0.1:11434/v1",
            "openai_api_key": "sk-test-secret-value",
            "extraction_provider": "openai",
            "extraction_model": "gpt-4o-mini",
            "summary_provider": "local",
            "summary_model": "",
        },
    )
    pdf_path = tmp_path / "typed.pdf"
    write_pdf(
        pdf_path,
        [
            f"Patient name: {BAIT['name']}",
            f"Email: {BAIT['email']}",
            "Collected: 2025-11-02",
            "Panel: Complete blood count",
            "RESULTS",
            "Test | Result | Unit | Reference interval | Flag",
            "Hemoglobin | 12.4 | g/dL | 13.0-17.0 | L",
        ],
    )
    home = client.get("/")
    assert "to OpenAI" in home.text
    uploaded = client.post(
        "/upload",
        data={"csrf": _csrf(home.text)},
        files={"report": ("typed.pdf", pdf_path.read_bytes(), "application/pdf")},
        follow_redirects=False,
    )
    assert uploaded.status_code == 303
    review = client.get("/review")
    assert "11.1" in review.text
    assert "12.4" not in review.text
    assert "sent to OpenAI" in review.text
    for bait in BAIT.values():
        assert bait not in review.text
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test-secret-value"
    assert BAIT["email"] in seen["body"]
    assert "Hemoglobin | 12.4" in seen["body"]
    assert "gpt-4o-mini" in seen["body"]


def test_upload_without_a_model_does_not_call_one(tmp_path: Path) -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(500)

    client = _app(tmp_path, handler)
    _register(client, "ada@example.com")
    pdf_path = tmp_path / "note.pdf"
    _prose_pdf(pdf_path)
    home = client.get("/")
    uploaded = client.post(
        "/upload",
        data={"csrf": _csrf(home.text)},
        files={"report": ("note.pdf", pdf_path.read_bytes(), "application/pdf")},
        follow_redirects=True,
    )
    assert called["n"] == 0
    assert "Choose an extraction model" in uploaded.text


def test_summary_discards_a_json_echo(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        sheet = '{"changes": [{"analyte": "hemoglobin", "delta": "+1.2", "latest_value": "13.6"}]}'
        return httpx.Response(200, json={"choices": [{"message": {"content": sheet}}]})

    client = _app(tmp_path, handler)
    _register(client, "ada@example.com")
    from app.pdfgen import write_fixtures

    write_fixtures(tmp_path / "fixtures")
    home = client.get("/")
    client.post("/demo", data={"csrf": _csrf(home.text)})
    settings_page = client.get("/settings")
    client.post(
        "/settings",
        data={
            "csrf": _csrf(settings_page.text),
            "local_base_url": "http://127.0.0.1:11434/v1",
            "openai_api_key": "sk-test-secret-value",
            "extraction_provider": "local",
            "extraction_model": "",
            "summary_provider": "openai",
            "summary_model": "gpt-4o-mini",
        },
    )
    page = client.get("/")
    shown = client.post("/summary", data={"csrf": _csrf(page.text)}, follow_redirects=True)
    assert "outside_supplied_interval" not in shown.text
    assert "returned the fact sheet" in shown.text
    assert "No summary yet" in shown.text


def test_summary_uses_the_fact_sheet_and_drops_new_numbers(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        calls.append(body)
        if len(calls) == 1:
            text = "Hemoglobin moved from 12.4 to 13.6 g/dL."
        else:
            text = "A new marker scored 99999."
        assert request.headers["authorization"] == "Bearer sk-test-secret-value"
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    client = _app(tmp_path, handler)
    _register(client, "ada@example.com")
    from app.pdfgen import write_fixtures

    write_fixtures(tmp_path / "fixtures")
    home = client.get("/")
    client.post("/demo", data={"csrf": _csrf(home.text)})
    settings_page = client.get("/settings")
    client.post(
        "/settings",
        data={
            "csrf": _csrf(settings_page.text),
            "local_base_url": "http://127.0.0.1:11434/v1",
            "openai_api_key": "sk-test-secret-value",
            "extraction_provider": "local",
            "extraction_model": "",
            "summary_provider": "openai",
            "summary_model": "gpt-4o-mini",
        },
    )
    page = client.get("/")
    client.post("/summary", data={"csrf": _csrf(page.text)})
    shown = client.get("/")
    assert "Hemoglobin moved from 12.4 to 13.6 g/dL." in shown.text
    assert "ada@example.com" not in calls[0]
    for bait in BAIT.values():
        assert bait not in calls[0]
    assert "12.4" in calls[0]
    after = client.post(
        "/summary",
        data={"csrf": _csrf(shown.text)},
        follow_redirects=True,
    )
    assert "99999" not in after.text
    assert "discarded" in after.text
    assert "Hemoglobin moved from 12.4 to 13.6 g/dL." in after.text

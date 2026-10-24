from __future__ import annotations

import io

from web_app import create_app


def test_convert_requires_a_file() -> None:
    client = create_app().test_client()

    response = client.post("/api/convert")

    assert response.status_code == 400
    assert response.get_json() == {"error": "Choose a PDF file first."}


def test_convert_rejects_non_pdf() -> None:
    client = create_app().test_client()

    response = client.post(
        "/api/convert",
        data={"pdf": (io.BytesIO(b"hello"), "notes.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Only PDF files are supported."}

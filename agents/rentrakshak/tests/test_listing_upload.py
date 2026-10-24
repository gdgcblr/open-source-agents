import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from rentrakshak.api.server import app
from rentrakshak.services.listing_upload import process_listing_upload

client = TestClient(app)


def test_upload_txt():
    r = client.post(
        "/api/upload-listing",
        files={"file": ("listing.txt", b"2 BHK HSR Layout rent 35000 deposit 3 months", "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "HSR" in data["extracted_text"]
    assert data["ocr_applied"] is False


def test_upload_image_mock_vision(monkeypatch):
    monkeypatch.setenv("RENTRAKSHAK_VISION_BACKEND", "mock")
    monkeypatch.setenv(
        "RENTRAKSHAK_MOCK_OCR_TEXT",
        "URGENT token pay today Koramangala 2BHK rent 15000 send OTP",
    )
    img = Image.new("RGB", (120, 40), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()
    out = process_listing_upload(raw, "screenshot.png")
    assert out["ocr_applied"] is True
    assert "Koramangala" in out["extracted_text"]
    assert out.get("preview_base64")


def test_upload_image_api_mock(monkeypatch):
    monkeypatch.setenv("RENTRAKSHAK_VISION_BACKEND", "mock")
    monkeypatch.setenv("RENTRAKSHAK_MOCK_OCR_TEXT", "Whitefield 3BHK semi furnished rent 45000")
    img = Image.new("RGB", (80, 80), color=(200, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    r = client.post(
        "/api/upload-listing",
        files={"file": ("nobroker.jpg", buf.getvalue(), "image/jpeg")},
    )
    assert r.status_code == 200
    assert r.json()["ocr_applied"] is True
    assert "Whitefield" in r.json()["extracted_text"]

from fastapi.testclient import TestClient

from rentrakshak.api.server import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_safety_report():
    r = client.post(
        "/api/safety-report",
        json={"listing_text": "URGENT pay token. Send OTP. Koramangala 2BHK rent 15000"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["risk_category"] == "critical_warning"
    assert data["findings"]


def test_index_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "RentRakshak" in r.text

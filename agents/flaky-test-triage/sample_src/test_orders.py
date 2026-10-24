import requests

BASE_URL = "https://qa-api.internal"


def test_create_user():
    payload = {"email": "qa.user@example.com", "name": "QA User"}
    resp = requests.post(f"{BASE_URL}/users", json=payload)
    assert resp.status_code == 201

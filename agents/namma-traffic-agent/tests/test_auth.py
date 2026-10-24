"""
test_auth.py - Unit tests for Google Gmail and Mobile OTP authentication
"""

import pytest
from starlette.testclient import TestClient
from server import app

client = TestClient(app)


def test_google_login_valid():
    res = client.post("/api/auth/google", json={
        "email": "shaik.commuter@gmail.com",
        "name": "Shaik Commuter"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["user"]["email"] == "shaik.commuter@gmail.com"
    assert data["user"]["provider"] == "google"
    assert "token" in data["user"]
    assert data["user"]["smart_card_balance"] == 280


def test_google_login_invalid_email():
    res = client.post("/api/auth/google", json={
        "email": "invalid_email_format"
    })
    assert res.status_code == 400


def test_otp_send_and_verify():
    # 1. Send OTP
    send_res = client.post("/api/auth/otp/send", json={
        "phone": "+919876543210"
    })
    assert send_res.status_code == 200
    send_data = send_res.json()
    assert send_data["status"] == "success"
    demo_otp = send_data["demo_otp"]
    assert len(demo_otp) == 6

    # 2. Verify with correct OTP
    verify_res = client.post("/api/auth/otp/verify", json={
        "phone": "+919876543210",
        "otp": demo_otp
    })
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["status"] == "success"
    assert verify_data["user"]["provider"] == "mobile_otp"
    assert "token" in verify_data["user"]


def test_otp_verify_invalid():
    res = client.post("/api/auth/otp/verify", json={
        "phone": "+919999999999",
        "otp": "000000"
    })
    assert res.status_code == 400

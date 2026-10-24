"""Synthetic identities only. No Google accounts, real credentials, or API calls."""

from datetime import datetime, timedelta, timezone
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth.crypt import RSASigner
from google.auth.exceptions import GoogleAuthError
from google.auth.jwt import encode
import pytest

import app as web
import auth


def begin_login(client):
    client.get("/")
    with client.session_transaction() as cookie:
        csrf = cookie["csrf"]
    response = client.post("/auth/google", data={"csrf_token": csrf})
    assert response.status_code == 302
    return parse_qs(urlparse(response.location).query)["state"][0]


def sign_in(client, monkeypatch):
    monkeypatch.setattr(web, "exchange_identity", lambda *args: {"google_sub": "synthetic-subject", "email": "person@example.test"})
    state = begin_login(client)
    response = client.get("/oauth/callback", query_string={"state": state, "code": "synthetic-code"})
    assert response.status_code == 302
    return state


def test_google_redirect_requests_identity_only(application):
    client = application.test_client()
    client.get("/")
    with client.session_transaction() as cookie:
        csrf = cookie["csrf"]
    result = client.post("/auth/google", data={"csrf_token": csrf})
    query = parse_qs(urlparse(result.location).query)
    # OAuth starts with a same-origin POST that redirects to Google's trusted origin.
    policy = result.headers["Content-Security-Policy"]
    assert "form-action 'self' https://accounts.google.com" in policy
    assert "*" not in policy
    assert set(query["scope"][0].split()) == set(auth.LOGIN_SCOPES)
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] and query["state"]
    assert "calendar" not in query["scope"][0]


def test_account_created_and_callback_cannot_be_replayed(application, monkeypatch):
    client = application.test_client()
    state = sign_in(client, monkeypatch)
    assert client.get("/api/me").json["user"]["email"] == "person@example.test"
    with client.session_transaction() as cookie:
        assert "person@example.test" not in str(dict(cookie))
        assert "synthetic-code" not in str(dict(cookie))
    assert client.get("/oauth/callback", query_string={"state": state, "code": "synthetic-code"}).status_code == 400


def test_callback_is_bound_to_original_browser(application):
    first, other = application.test_client(), application.test_client()
    state = begin_login(first)
    response = other.get("/oauth/callback", query_string={"state": state, "code": "synthetic-code"})
    assert response.status_code == 400
    assert other.get("/api/me").status_code == 401


def test_expired_oauth_state_is_rejected(application):
    client = application.test_client()
    state = begin_login(client)
    with application.extensions["store"].connect() as db:
        db.execute("UPDATE oauth_requests SET expires=0")
    assert client.get("/oauth/callback", query_string={"state": state, "code": "synthetic-code"}).status_code == 400


def test_user_declining_access_does_not_log_query(application, caplog):
    client = application.test_client()
    state = begin_login(client)
    result = client.get("/oauth/callback", query_string={"state": state, "error": "access_denied", "error_description": "private-payload"})
    assert result.status_code == 400
    assert "private-payload" not in caplog.text
    assert client.get("/api/me").status_code == 401


def test_failed_token_exchange_does_not_log_sensitive_error(application, monkeypatch, caplog):
    def fail(*args):
        raise ValueError("private-token-value")
    monkeypatch.setattr(web, "exchange_identity", fail)
    client = application.test_client()
    state = begin_login(client)
    response = client.get("/oauth/callback", query_string={"state": state, "code": "private-code-value"})
    assert response.status_code == 400
    assert "private-token-value" not in response.text + caplog.text
    assert "private-code-value" not in response.text + caplog.text


def test_logout_revokes_copied_session_cookie(application, monkeypatch):
    client = application.test_client()
    sign_in(client, monkeypatch)
    copied_cookie = client.get_cookie("session").value
    client.get("/")
    with client.session_transaction() as cookie:
        csrf = cookie["csrf"]
    assert client.post("/logout", data={"csrf_token": csrf}).status_code == 302
    replay = application.test_client()
    replay.set_cookie("session", copied_cookie)
    assert replay.get("/api/me").status_code == 401


def test_login_and_logout_require_csrf(application):
    client = application.test_client()
    assert client.post("/auth/google").status_code == 403
    assert client.post("/logout").status_code == 403
    assert client.get("/logout").status_code == 405


def test_google_subject_is_account_key_not_email(application):
    store = application.extensions["store"]
    token = store.create_login({"google_sub": "same-subject", "email": "first@example.test"})
    first_id = store.current_user(token)["id"]
    second = store.create_login({"google_sub": "same-subject", "email": "updated@example.test"})
    assert store.current_user(second)["id"] == first_id
    assert store.current_user(second)["email"] == "updated@example.test"


def test_missing_configuration_disables_login(application, tmp_path):
    application.config["GOOGLE_CLIENT_CONFIG"] = str(tmp_path / "missing.json")
    client = application.test_client()
    assert "Google sign-in not configured" in client.get("/").text
    with client.session_transaction() as cookie:
        csrf = cookie["csrf"]
    assert client.post("/auth/google", data={"csrf_token": csrf}).status_code == 503


def test_security_headers_and_host_validation(application):
    client = application.test_client()
    response = client.get("/")
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    assert client.get("/", base_url="http://attacker.example").status_code == 400


@pytest.fixture(scope="module")
def signing_material():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-test")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1)).sign(key, hashes.SHA256()))
    signer = RSASigner.from_string(key.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), key_id="test")
    return signer, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.mark.parametrize("bad_claim", [None, "aud", "iss", "exp", "nonce", "email_verified"])
def test_real_signature_verification_and_identity_claims(config_file, signing_material, monkeypatch, bad_claim):
    signer, certificate = signing_material
    claims = {"iss": "https://accounts.google.com", "aud": "synthetic-client.apps.googleusercontent.com",
              "iat": int(time.time()), "exp": int(time.time()) + 300, "sub": "synthetic-subject",
              "email": "person@example.test", "email_verified": True, "nonce": "expected-nonce"}
    if bad_claim:
        claims[bad_claim] = {"aud": "another-client", "iss": "https://attacker.example", "exp": 1,
                             "nonce": "wrong-nonce", "email_verified": False}[bad_claim]
    token = encode(signer, claims).decode()
    flow = SimpleNamespace(fetch_token=Mock(), oauth2session=SimpleNamespace(token={"id_token": token}))
    monkeypatch.setattr(auth, "google_flow", lambda *args: flow)
    certificates = SimpleNamespace(status=200, data=json.dumps({"test": certificate}).encode())
    monkeypatch.setattr(auth, "Request", lambda: lambda *args, **kwargs: certificates)
    config = auth.client_configuration(str(config_file), "http://127.0.0.1:5000/oauth/callback")
    pending = {"state": "test-state", "verifier": "test-verifier", "nonce": "expected-nonce"}
    if bad_claim:
        with pytest.raises((ValueError, GoogleAuthError)):
            auth.exchange_identity(config, "http://127.0.0.1:5000/oauth/callback", pending, "test-code")
    else:
        assert auth.exchange_identity(config, "http://127.0.0.1:5000/oauth/callback", pending, "test-code") == {
            "google_sub": "synthetic-subject", "email": "person@example.test"}


def test_forged_token_is_rejected(config_file, signing_material, monkeypatch):
    signer, certificate = signing_material
    token = encode(signer, {"aud": "synthetic-client.apps.googleusercontent.com", "iat": int(time.time()),
                            "exp": int(time.time()) + 300}).decode()
    parts = token.split(".")
    parts[2] = "A" * len(parts[2])
    flow = SimpleNamespace(fetch_token=Mock(), oauth2session=SimpleNamespace(token={"id_token": ".".join(parts)}))
    monkeypatch.setattr(auth, "google_flow", lambda *args: flow)
    monkeypatch.setattr(auth, "Request", lambda: lambda *a, **kw: SimpleNamespace(status=200, data=json.dumps({"test": certificate}).encode()))
    config = auth.client_configuration(str(config_file), "http://127.0.0.1:5000/oauth/callback")
    with pytest.raises(ValueError):
        auth.exchange_identity(config, "http://127.0.0.1:5000/oauth/callback",
                               {"state": "test", "verifier": "test", "nonce": "test"}, "test")

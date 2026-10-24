"""Calendar boundary tests use synthetic identities and an in-memory keychain."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from google.oauth2.credentials import Credentials
import pytest

import app as web
import auth
import calendar_api


@pytest.fixture
def vault(monkeypatch):
    entries = {}
    monkeypatch.setattr(web, "require_secure_keyring", lambda: None)
    monkeypatch.setattr(calendar_api, "require_secure_keyring", lambda: None)
    monkeypatch.setattr(calendar_api.keyring, "set_password", lambda service, owner, value: entries.__setitem__((service, owner), value))
    monkeypatch.setattr(calendar_api.keyring, "get_password", lambda service, owner: entries.get((service, owner)))
    monkeypatch.setattr(calendar_api.keyring, "delete_password", lambda service, owner: entries.pop((service, owner)))
    return entries


@pytest.fixture
def signed_in(application):
    client = application.test_client()
    token = application.extensions["store"].create_login({"google_sub": "test-google-subject", "email": "person@example.test"})
    with client.session_transaction() as cookie:
        cookie["login"] = token
    client.get("/")
    return client


def post(client, path, **fields):
    with client.session_transaction() as cookie:
        csrf = cookie["csrf"]
    return client.post(path, data={"csrf_token": csrf, **fields})


def credentials():
    return Credentials(token="synthetic-access-token", refresh_token="synthetic-refresh-token",
                       client_id="synthetic-client", client_secret="synthetic-secret",
                       token_uri="https://oauth2.googleapis.com/token",
                       scopes=[*auth.LOGIN_SCOPES, auth.CALENDAR_SCOPE],
                       expiry=datetime.now(timezone.utc) + timedelta(hours=1))


def connect(client, monkeypatch, subject="test-google-subject"):
    response = post(client, "/calendar/connect")
    assert response.status_code == 302
    state = parse_qs(urlparse(response.location).query)["state"][0]
    monkeypatch.setattr(web, "exchange_calendar", lambda *args: ({"google_sub": subject, "email": "person@example.test"}, credentials()))
    return client.get("/oauth/callback", query_string={"state": state, "code": "synthetic-code"})


def test_consent_requests_freebusy_without_event_read_or_write(signed_in, vault):
    response = post(signed_in, "/calendar/connect")
    query = parse_qs(urlparse(response.location).query)
    assert set(query["scope"][0].split()) == {*auth.LOGIN_SCOPES, auth.CALENDAR_SCOPE}
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert "consent" in query["prompt"][0]
    assert "calendar.events.owned" not in response.location


def test_tokens_stay_out_of_database_cookie_response_and_logs(application, signed_in, vault, monkeypatch, caplog):
    assert connect(signed_in, monkeypatch).status_code == 302
    assert len(vault) == 1
    user = signed_in.get("/api/me").json["user"]
    assert application.extensions["store"].calendar_connected(user["id"])
    with application.extensions["store"].connect() as db:
        dump = "\n".join(db.iterdump())
    with signed_in.session_transaction() as cookie:
        dump += str(dict(cookie))
    dump += signed_in.get("/").text + caplog.text
    assert "synthetic-access-token" not in dump
    assert "synthetic-refresh-token" not in dump
    assert "Calendar connected" in signed_in.get("/").text


def test_different_google_account_is_rejected(application, signed_in, vault, monkeypatch):
    response = connect(signed_in, monkeypatch, subject="another-google-subject")
    assert response.status_code == 403
    assert "same Google account" in response.text
    assert not vault
    user = signed_in.get("/api/me").json["user"]
    assert not application.extensions["store"].calendar_connected(user["id"])


def test_calendar_callback_requires_current_login(application, signed_in, vault):
    response = post(signed_in, "/calendar/connect")
    state = parse_qs(urlparse(response.location).query)["state"][0]
    with signed_in.session_transaction() as cookie:
        cookie.pop("login")
    result = signed_in.get("/oauth/callback", query_string={"state": state, "code": "test"})
    assert result.status_code == 401
    assert not vault


def test_calendar_callback_cannot_change_logged_in_owner(application, signed_in, vault):
    response = post(signed_in, "/calendar/connect")
    state = parse_qs(urlparse(response.location).query)["state"][0]
    second = application.extensions["store"].create_login({"google_sub": "second-subject", "email": "second@example.test"})
    with signed_in.session_transaction() as cookie:
        cookie["login"] = second
    result = signed_in.get("/oauth/callback", query_string={"state": state, "code": "test"})
    assert result.status_code == 403
    assert not vault


def test_calendar_actions_require_login_and_csrf(application):
    client = application.test_client()
    client.get("/")
    for endpoint in ("/calendar/connect", "/calendar/disconnect", "/calendar/availability"):
        assert client.post(endpoint).status_code == 403
        assert post(client, endpoint).status_code == 401


def test_disconnect_removes_only_current_users_tokens(application, signed_in, vault, monkeypatch):
    connect(signed_in, monkeypatch)
    vault[(calendar_api.SERVICE, "another-user")] = "another-user-token"
    response = post(signed_in, "/calendar/disconnect")
    assert response.status_code == 302
    assert list(vault) == [(calendar_api.SERVICE, "another-user")]
    user = signed_in.get("/api/me").json["user"]
    assert not application.extensions["store"].calendar_connected(user["id"])
    assert signed_in.get("/api/me").status_code == 200


def test_keychain_failure_does_not_mark_connection_complete(application, signed_in, vault, monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError("private-token-content")
    monkeypatch.setattr(web, "save_credentials", fail)
    result = connect(signed_in, monkeypatch)
    assert result.status_code == 503
    assert "private-token-content" not in result.text + caplog.text
    user = signed_in.get("/api/me").json["user"]
    assert not application.extensions["store"].calendar_connected(user["id"])


def test_api_only_calls_freebusy_and_strips_unexpected_fields(monkeypatch):
    calls = []
    body = {"calendars": {"primary": {"busy": [{"start": "2026-10-26T10:00:00+05:30", "end": "2026-10-26T11:00:00+05:30", "summary": "private-title"}],
                                           "description": "private-agenda"},
                           "shared@example.test": {"errors": [{"reason": "notFound"}]}}}

    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(status_code=200, json=lambda: body)

    monkeypatch.setattr(calendar_api.GoogleCalendar, "_session", lambda *args: Session())
    result = calendar_api.GoogleCalendar().availability("test-user", {
        "date_from": "2026-10-26", "date_to": "2026-10-26", "timezone": "Asia/Kolkata", "attendees": ["shared@example.test"]})
    assert {key: result[key] for key in ("busy", "unknown")} == {"busy": [{"start": "2026-10-26T10:00:00+05:30", "end": "2026-10-26T11:00:00+05:30"}], "unknown": 1}
    assert calls[0][0] == "https://www.googleapis.com/calendar/v3/freeBusy"
    assert len(calls) == 1
    assert calls[0][1]["json"]["items"] == [{"id": "primary"}, {"id": "shared@example.test"}]
    assert result["checks"] == [{"calendar": "primary", "status": "checked", "busy_count": 1},
                                {"calendar": "shared@example.test", "status": "unknown", "busy_count": None, "reason": "not_found_or_not_shared"}]
    assert "private-title" not in json.dumps(result)


def test_availability_page_queries_only_current_user(application, signed_in, vault, monkeypatch, caplog):
    connect(signed_in, monkeypatch)
    calls = []
    today = datetime.now(timezone.utc).date() + timedelta(days=1)

    def availability(owner, meeting):
        calls.append((owner, meeting))
        return {"busy": [{"start": f"{today}T10:00:00+05:30", "end": f"{today}T11:00:00+05:30"}], "unknown": 0}

    monkeypatch.setattr(application.extensions["calendar"], "availability", availability)
    result = post(signed_in, "/calendar/availability", date_from=str(today), date_to=str(today),
                  timezone="Asia/Kolkata", attendees="victim@example.test", owner="another-user")
    assert result.status_code == 200
    assert calls[0][0] == signed_in.get("/api/me").json["user"]["id"]
    assert calls[0][1]["attendees"] == []
    assert "Busy" in result.text
    assert "victim@example.test" not in result.text + caplog.text


@pytest.mark.parametrize("fields", [
    {"date_from": "invalid", "date_to": "invalid", "timezone": "Asia/Kolkata"},
    {"date_from": "2000-01-01", "date_to": "2000-01-01", "timezone": "Asia/Kolkata"},
    {"date_from": "2099-01-01", "date_to": "2099-02-01", "timezone": "Asia/Kolkata"},
    {"date_from": "2099-01-01", "date_to": "2099-01-01", "timezone": "Not/AZone"},
])
def test_invalid_availability_requests_never_call_google(application, signed_in, vault, monkeypatch, fields):
    connect(signed_in, monkeypatch)
    def fail(*args):
        pytest.fail("Invalid input reached Google")
    monkeypatch.setattr(application.extensions["calendar"], "availability", fail)
    assert post(signed_in, "/calendar/availability", **fields).status_code == 400


def test_calendar_exchange_rejects_partial_scope_or_missing_refresh_token(config_file, monkeypatch):
    config = json.loads(config_file.read_text())
    monkeypatch.setattr(auth, "verified_identity", lambda *args: {"google_sub": "test-subject", "email": "person@example.test"})
    for granted in (Credentials(token="test", scopes=auth.LOGIN_SCOPES, refresh_token="test"),
                    Credentials(token="test", scopes=[*auth.LOGIN_SCOPES, auth.CALENDAR_SCOPE],
                                granted_scopes=auth.LOGIN_SCOPES, refresh_token="test"),
                    Credentials(token="test", scopes=[auth.CALENDAR_SCOPE])):
        flow = SimpleNamespace(credentials=granted, fetch_token=lambda **kwargs: None)
        monkeypatch.setattr(auth, "google_flow", lambda *args, **kwargs: flow)
        with pytest.raises(ValueError):
            auth.exchange_calendar(config, "http://127.0.0.1:5000/oauth/callback",
                                   {"state": "test", "nonce": "test", "verifier": "test"}, "test")


@pytest.mark.parametrize("status,reasons,expected", [
    (403, ["SERVICE_DISABLED"], "api_disabled"),
    (403, ["accessNotConfigured"], "api_disabled"),
    (401, [], "access_expired"),
    (403, ["ACCESS_TOKEN_SCOPE_INSUFFICIENT"], "missing_scope"),
    (429, [], "rate_limited"),
    (500, [], "provider_error"),
])
def test_provider_error_messages_are_specific_without_leaking_content(status, reasons, expected):
    response = SimpleNamespace(status_code=status, json=lambda: {
        "error": {"message": "private-provider-content", "details": [{"reason": reason} for reason in reasons]}})
    error = calendar_api.availability_error(response)
    assert error.code == expected
    assert "private-provider-content" not in str(error)


def test_disabled_api_message_reaches_page_without_private_error(application, signed_in, vault, monkeypatch, caplog):
    connect(signed_in, monkeypatch)
    def fail(*args):
        response = SimpleNamespace(status_code=403, json=lambda: {
            "error": {"message": "private-provider-content", "details": [{"reason": "SERVICE_DISABLED"}]}})
        raise calendar_api.availability_error(response)
    monkeypatch.setattr(application.extensions["calendar"], "availability", fail)
    day = str(datetime.now(timezone.utc).date() + timedelta(days=1))
    result = post(signed_in, "/calendar/availability", date_from=day, date_to=day, timezone="Asia/Kolkata")
    assert result.status_code == 502
    assert "Google Calendar API is disabled" in result.text
    assert "private-provider-content" not in result.text + caplog.text
    assert "category=api_disabled" in caplog.text


def test_refreshed_credentials_are_saved_only_in_keychain(vault, monkeypatch):
    calendar_api.save_credentials("test-owner", credentials())
    class Session:
        def __init__(self, credential, **kwargs):
            self.credentials = credential
            assert kwargs["refresh_timeout"] == 15
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(calendar_api, "AuthorizedSession", Session)
    with calendar_api.GoogleCalendar()._session("test-owner") as client:
        client.credentials.token = "synthetic-refreshed-token"
    saved = json.loads(vault[(calendar_api.SERVICE, "test-owner")])
    assert saved["token"] == "synthetic-refreshed-token"


def test_shared_secondary_mapping_is_used_for_availability_only(monkeypatch):
    mapped_id = 'synthetic-shared-calendar@group.calendar.google.com'
    monkeypatch.setenv('ATTENDEE_CALENDAR_IDS', json.dumps({'invitee@example.test': mapped_id}))
    calls = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, **kwargs):
            calls.append(kwargs['json'])
            return SimpleNamespace(status_code=200, json=lambda: {'calendars': {
                'primary': {'busy': []}, mapped_id: {'busy': [
                    {'start': '2026-10-26T10:00:00+05:30', 'end': '2026-10-26T11:00:00+05:30'}]}}})
    monkeypatch.setattr(calendar_api.GoogleCalendar, '_session', lambda *args: Session())
    result = calendar_api.GoogleCalendar().availability('owner', {'date_from': '2026-10-26',
        'date_to': '2026-10-26', 'timezone': 'Asia/Kolkata', 'attendees': ['invitee@example.test']})
    assert calls[0]['items'] == [{'id': 'primary'}, {'id': mapped_id}]
    assert result['unknown'] == 0
    assert len(result['busy']) == 1
    assert result['checks'][1] == {'calendar': 'invitee@example.test', 'status': 'checked', 'busy_count': 1, 'shared_calendar': True}
    assert mapped_id not in json.dumps(result)


@pytest.mark.parametrize('mapping', ['[]', '{"invitee@example.test":"https://example.test/private"}', '{"invalid":"calendar@group.calendar.google.com"}'])
def test_invalid_calendar_mapping_fails_closed(monkeypatch, mapping):
    monkeypatch.setenv('ATTENDEE_CALENDAR_IDS', mapping)
    with pytest.raises(calendar_api.CalendarError, match='ATTENDEE_CALENDAR_IDS'):
        calendar_api.GoogleCalendar()

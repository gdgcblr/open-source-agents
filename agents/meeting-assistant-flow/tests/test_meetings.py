"""End-to-end Flask workflow tests; every calendar write stays synthetic."""

from datetime import datetime, timedelta, timezone
import json
import time

from google.oauth2.credentials import Credentials
import pytest

import app as web
import auth
import meetings as workflow
from calendar_api import BookingUncertain, CalendarError, GoogleCalendar
from test_calendar import post, signed_in


class Calendar:
    def __init__(self):
        self.busy = []
        self.unknown = 0
        self.created = []
        self.failure = None
        self.existing = None

    def availability(self, owner, meeting):
        return {"busy": self.busy, "unknown": self.unknown}

    def create(self, owner, draft_id, meeting, slot):
        self.created.append((owner, draft_id, dict(meeting), dict(slot)))
        if self.failure:
            raise self.failure
        self.existing = {"id": draft_id, "url": "https://calendar.google.com/calendar/event?eid=synthetic"}
        return self.existing

    def lookup(self, owner, draft_id):
        return self.existing


@pytest.fixture
def calendar(application, signed_in, monkeypatch):
    result = Calendar()
    application.extensions["calendar"] = result
    owner = signed_in.get("/api/me").json["user"]["id"]
    application.extensions["store"].set_calendar_connected(owner, True, can_write=True)

    async def slots(meeting, busy):
        return [{"start": f"{meeting['date_from']}T10:00:00+05:30",
                 "end": f"{meeting['date_from']}T10:30:00+05:30"}]

    monkeypatch.setattr(workflow, "get_slots", slots)
    return result


def fields():
    day = str(datetime.now(timezone.utc).date() + timedelta(days=2))
    return {"title": "Project kickoff", "purpose": "Agree on scope and responsibilities",
            "agenda": "Goals — 5 min\nScope — 15 min\nResponsibilities — 10 min",
            "attendees": "invitee@example.test", "duration": "30", "timezone": "Asia/Kolkata",
            "date_from": day, "date_to": day, "hour_start": "9", "hour_end": "17", "include_weekends": "on"}


def current(application, client):
    with client.session_transaction() as cookie:
        draft_id = cookie["draft_id"]
    owner = client.get("/api/me").json["user"]["id"]
    return application.extensions["store"].get(draft_id, owner)


def ready(application, client):
    assert post(client, "/meetings/new", **fields()).status_code == 302
    item = current(application, client)
    assert post(client, f"/meetings/{item['id']}/slots", version=item["version"]).status_code == 302
    item = current(application, client)
    assert post(client, f"/meetings/{item['id']}/preview", version=item["version"], slot="0").status_code == 302
    return current(application, client)


def approve(client, item, **overrides):
    values = {"version": item["version"], "review_token": item["data"]["review_token"], "approved": "yes", **overrides}
    return post(client, f"/meetings/{item['id']}/confirm", **values)


def test_full_workflow_and_repeated_confirm_do_not_duplicate(application, signed_in, calendar):
    item = ready(application, signed_in)
    preview = signed_in.get(f"/meetings/{item['id']}/review")
    assert preview.status_code == 200
    assert "invitee@example.test" in preview.text
    assert "Create meeting and send invitations" in preview.text
    assert approve(signed_in, item).status_code == 302
    assert current(application, signed_in)["status"] == "created"
    assert len(calendar.created) == 1
    assert approve(signed_in, item).status_code == 302
    assert len(calendar.created) == 1
    assert calendar.created[0][2]["title"] == fields()["title"]


@pytest.mark.parametrize("change", [{"approved": "no"}, {"review_token": "forged"}, {"version": 0}])
def test_confirmation_requires_exact_review_and_explicit_approval(application, signed_in, calendar, change):
    item = ready(application, signed_in)
    assert approve(signed_in, item, **change).status_code == 409
    assert not calendar.created


def test_editing_draft_invalidates_slot_and_old_approval(application, signed_in, calendar):
    item = ready(application, signed_in)
    response = post(signed_in, f"/meetings/{item['id']}/save", version=item["version"], **{**fields(), "title": "Updated kickoff"})
    assert response.status_code == 302
    assert "selected" not in current(application, signed_in)["data"]
    assert approve(signed_in, item).status_code == 409
    assert not calendar.created


def test_new_conflict_prevents_calendar_write(application, signed_in, calendar):
    item = ready(application, signed_in)
    calendar.busy = [item["data"]["selected"]]
    assert approve(signed_in, item).status_code == 409
    assert current(application, signed_in)["status"] == "draft"
    assert not calendar.created


def test_unknown_attendees_require_acknowledgement(application, signed_in, calendar):
    calendar.unknown = 1
    item = ready(application, signed_in)
    assert approve(signed_in, item).status_code == 400
    assert not calendar.created
    assert approve(signed_in, item, ack_unknown="yes").status_code == 302
    assert len(calendar.created) == 1


def test_newly_unknown_availability_requires_new_review(application, signed_in, calendar):
    item = ready(application, signed_in)
    calendar.unknown = 1
    assert approve(signed_in, item).status_code == 409
    assert not calendar.created


def test_write_consent_is_required_even_if_client_posts_approval(application, signed_in, calendar):
    item = ready(application, signed_in)
    owner = signed_in.get("/api/me").json["user"]["id"]
    application.extensions["store"].set_calendar_connected(owner, True, can_write=False)
    assert approve(signed_in, item).status_code == 403
    assert not calendar.created


def test_other_users_cannot_read_or_confirm_a_draft(application, signed_in, calendar):
    item = ready(application, signed_in)
    other = application.test_client()
    token = application.extensions["store"].create_login({"google_sub": "other-subject", "email": "other@example.test"})
    with other.session_transaction() as cookie:
        cookie["login"] = token
    other.get("/")
    assert other.get(f"/meetings/{item['id']}/review").status_code == 404
    assert approve(other, item).status_code == 404
    assert not calendar.created


def test_in_progress_creation_rejects_second_submission(application, signed_in, calendar):
    item = ready(application, signed_in)
    owner = signed_in.get("/api/me").json["user"]["id"]
    application.extensions["store"].claim(item["id"], owner, item["version"])
    assert approve(signed_in, item).status_code == 409
    assert not calendar.created


def test_status_change_during_preflight_cancels_stale_write(application, signed_in, calendar, monkeypatch):
    item = ready(application, signed_in)
    owner = signed_in.get("/api/me").json["user"]["id"]
    def recovered_during_recheck(*args):
        data = item["data"]
        data["attempted"] = True
        application.extensions["store"].finish(item["id"], owner, data, "ready")
        return {"busy": [], "unknown": 0}
    monkeypatch.setattr(calendar, "availability", recovered_during_recheck)
    assert approve(signed_in, item).status_code == 409
    assert not calendar.created


def test_uncertain_creation_is_reconciled_without_second_write(application, signed_in, calendar):
    item = ready(application, signed_in)
    calendar.failure = TimeoutError("private-network-content")
    assert approve(signed_in, item).status_code == 302
    assert current(application, signed_in)["status"] == "unknown"
    calendar.existing = {"id": item["id"], "url": ""}
    response = post(signed_in, f"/meetings/{item['id']}/reconcile")
    assert response.status_code == 302
    assert current(application, signed_in)["status"] == "created"
    assert len(calendar.created) == 1


def test_unknown_not_found_retry_preserves_immutable_snapshot_and_id(application, signed_in, calendar):
    item = ready(application, signed_in)
    calendar.failure = BookingUncertain("Check status")
    approve(signed_in, item)
    post(signed_in, f"/meetings/{item['id']}/reconcile")
    retry = current(application, signed_in)
    assert retry["status"] == "ready"
    assert retry["data"]["attempted"]
    assert post(signed_in, f"/meetings/{item['id']}/save", version=retry["version"], **fields()).status_code == 409
    calendar.failure = None
    assert approve(signed_in, retry).status_code == 302
    assert [call[1] for call in calendar.created] == [item["id"], item["id"]]


@pytest.mark.parametrize("secret", ["password=hunter2", '"password": "not-allowed"', "my password is not-allowed", "-----BEGIN ENCRYPTED PRIVATE KEY-----", "api_key=example-value", "ENC[encrypted-content]"])
def test_secret_input_is_rejected_before_draft_storage(application, signed_in, calendar, secret):
    response = post(signed_in, "/meetings/new", **{**fields(), "purpose": secret})
    assert response.status_code == 400
    assert secret not in response.text
    with application.extensions["store"].connect() as db:
        assert db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 0


def test_agenda_generation_requires_data_sharing_consent(application, signed_in, calendar, monkeypatch):
    item = ready(application, signed_in)
    async def fail(*args):
        pytest.fail("Model was called without consent")
    monkeypatch.setattr(workflow, "prepare_agenda", fail)
    assert post(signed_in, f"/meetings/{item['id']}/agenda", version=item["version"], message="Prepare agenda").status_code == 400


def test_ai_agenda_is_editable_and_invalidates_previous_preview(application, signed_in, calendar, monkeypatch):
    item = ready(application, signed_in)
    async def propose(*args):
        return {"title": "Focused kickoff", "agenda": "Discuss scope — 30 minutes", "reply": "A focused agenda is ready."}
    monkeypatch.setattr(workflow, "prepare_agenda", propose)
    response = post(signed_in, f"/meetings/{item['id']}/agenda", version=item["version"], ai_consent="yes", message="Focus on scope")
    assert response.status_code == 302
    updated = current(application, signed_in)
    assert updated["data"]["meeting"]["agenda"] == "Discuss scope — 30 minutes"
    assert "selected" not in updated["data"]
    assert not calendar.created


def test_secret_in_model_output_is_not_saved(application, signed_in, calendar, monkeypatch):
    item = ready(application, signed_in)
    async def propose(*args):
        return {"title": "Kickoff", "agenda": "password=not-allowed", "reply": "Done"}
    monkeypatch.setattr(workflow, "prepare_agenda", propose)
    assert post(signed_in, f"/meetings/{item['id']}/agenda", version=item["version"], ai_consent="yes").status_code == 400
    assert "not-allowed" not in json.dumps(current(application, signed_in))


def test_scheduling_consent_requests_event_scope(application, signed_in, calendar, monkeypatch):
    monkeypatch.setattr(web, "require_secure_keyring", lambda: None)
    response = post(signed_in, "/calendar/enable-scheduling")
    from urllib.parse import parse_qs, urlparse
    assert response.status_code == 302
    assert set(parse_qs(urlparse(response.location).query)["scope"][0].split()) == {
        *auth.LOGIN_SCOPES, auth.CALENDAR_SCOPE, auth.WRITE_SCOPE}


def test_calendar_payload_uses_approved_fields_and_same_event_id(monkeypatch):
    from types import SimpleNamespace
    calls = []
    draft_id = "a" * 32
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(status_code=201, json=lambda: {"id": draft_id, "htmlLink": "https://calendar.google.com/calendar/event?eid=test"})
    monkeypatch.setattr(GoogleCalendar, "_session", lambda *args: Session())
    meeting = {**fields(), "attendees": ["invitee@example.test"]}
    selected = {"start": "2099-01-01T10:00:00+05:30", "end": "2099-01-01T10:30:00+05:30"}
    event = GoogleCalendar().create("owner", draft_id, meeting, selected)
    assert event["id"] == draft_id
    payload = calls[0][1]["json"]
    assert payload["id"] == draft_id
    assert payload["summary"] == meeting["title"]
    assert calls[0][1]["params"] == {"sendUpdates": "all"}
    assert payload["guestsCanSeeOtherGuests"] is False


def test_reconcile_requests_only_app_event_reference(monkeypatch):
    from types import SimpleNamespace
    calls = []
    draft_id = "b" * 32
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(status_code=200, json=lambda: {"id": draft_id, "extendedProperties": {"private": {"meetingAssistantDraft": draft_id}}})
    monkeypatch.setattr(GoogleCalendar, "_session", lambda *args: Session())
    assert GoogleCalendar().lookup("owner", draft_id)["id"] == draft_id
    assert calls[0][0].endswith("/events/" + draft_id)
    assert calls[0][1]["params"]["fields"] == "id,htmlLink,status,extendedProperties"

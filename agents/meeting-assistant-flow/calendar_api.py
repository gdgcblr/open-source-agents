"""Free/busy queries and approved writes; never list existing meeting details."""

from datetime import date, datetime, time, timedelta
from contextlib import contextmanager
from html import escape
import json
import os
import re
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import keyring
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from auth import CALENDAR_SCOPE, WRITE_SCOPE

BASE = "https://www.googleapis.com/calendar/v3"
SCOPES = [CALENDAR_SCOPE]
SERVICE = "meeting-assistant-flow"


class CalendarError(Exception):
    def __init__(self, message, code="calendar_error"):
        super().__init__(message)
        self.code = code


class BookingUncertain(CalendarError):
    """A request may have reached Google. Reconcile before sending anything again."""


def availability_error(response):
    """Map provider categories to our own messages. Never display raw API errors."""
    try:
        error = response.json().get("error", {})
        reasons = {entry.get("reason") for entry in error.get("errors", []) + error.get("details", [])}
    except (ValueError, TypeError, AttributeError):
        reasons = set()
    if reasons & {"SERVICE_DISABLED", "accessNotConfigured"}:
        return CalendarError(
            "Google Calendar API is disabled for your OAuth project's credentials. "
            "Open that project in Google Cloud Console, enable Google Calendar API, "
            "then retry this check. You do not need to reconnect Calendar.", "api_disabled")
    if response.status_code == 401:
        return CalendarError("Calendar access expired or was revoked. Disconnect Calendar locally and reconnect it.", "access_expired")
    if reasons & {"ACCESS_TOKEN_SCOPE_INSUFFICIENT", "insufficientPermissions"}:
        return CalendarError("Availability permission is missing. Reconnect Calendar and approve free/busy access.", "missing_scope")
    if response.status_code == 429 or "rateLimitExceeded" in reasons:
        return CalendarError("Google Calendar's request limit was reached. Wait a little and try again.", "rate_limited")
    return CalendarError("Google Calendar could not return availability. Try again or reconnect Calendar.", "provider_error")


def require_secure_keyring():
    # Explicitly allow OS stores; never silently fall back to plaintext files.
    module = type(keyring.get_keyring()).__module__
    if module not in {"keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService"}:
        raise CalendarError("Configure an OS credential store before connecting Google Calendar.")


def save_credentials(owner, credentials):
    require_secure_keyring()
    payload = json.loads(credentials.to_json())
    payload.pop("id_token", None)
    granted = credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes
    if isinstance(granted, str):
        granted = granted.split()
    payload["scopes"] = [scope for scope in (CALENDAR_SCOPE, WRITE_SCOPE) if scope in (granted or [])]
    keyring.set_password(SERVICE, owner, json.dumps(payload))


def disconnect(owner):
    require_secure_keyring()
    if keyring.get_password(SERVICE, owner):
        keyring.delete_password(SERVICE, owner)


class GoogleCalendar:
    def __init__(self):
        try:
            mapping = json.loads(os.getenv("ATTENDEE_CALENDAR_IDS", "{}"))
            if not isinstance(mapping, dict) or len(mapping) > 50:
                raise ValueError
            self.calendar_ids = {}
            for email, calendar_id in mapping.items():
                if (not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
                        or not isinstance(calendar_id, str) or len(calendar_id) > 254
                        or not re.fullmatch(r"[A-Za-z0-9_.+-]+@group\.calendar\.google\.com", calendar_id)):
                    raise ValueError
                self.calendar_ids[email.lower()] = calendar_id
        except (ValueError, TypeError):
            raise CalendarError("ATTENDEE_CALENDAR_IDS must map attendee emails to valid secondary Calendar IDs.", "invalid_calendar_mapping") from None

    @contextmanager
    def _session(self, owner, require_write=False):
        require_secure_keyring()
        saved = keyring.get_password(SERVICE, owner)
        if not saved:
            raise CalendarError("Connect Google Calendar first.")
        credentials = Credentials.from_authorized_user_info(json.loads(saved))
        if require_write and not credentials.has_scopes([WRITE_SCOPE]):
            raise CalendarError("Enable scheduling and approve Calendar event access before creating invitations.", "write_required")
        original_token = credentials.token
        with AuthorizedSession(credentials, refresh_timeout=15, max_refresh_attempts=1) as client:
            yield client
        if credentials.token != original_token:
            save_credentials(owner, credentials)

    def connected(self, owner):
        try:
            require_secure_keyring()
            return bool(keyring.get_password(SERVICE, owner))
        except Exception:
            return False

    def availability(self, owner, meeting):
        zone = ZoneInfo(meeting["timezone"])
        start = datetime.combine(date.fromisoformat(meeting["date_from"]), time.min, zone)
        end = datetime.combine(date.fromisoformat(meeting["date_to"]) + timedelta(days=1), time.min, zone)
        labels = ["primary", *meeting["attendees"]]
        calendar_ids = [self.calendar_ids.get(label.lower(), label) for label in labels]
        with self._session(owner) as client:
            response = client.post(f"{BASE}/freeBusy", json={
                "timeMin": start.isoformat(), "timeMax": end.isoformat(), "timeZone": meeting["timezone"],
                "items": [{"id": calendar_id} for calendar_id in dict.fromkeys(calendar_ids)],
            }, timeout=15)
            if response.status_code != 200:
                raise availability_error(response)
            calendars = response.json().get("calendars", {})
        busy, unknown, checks = [], 0, []
        for label, calendar_id in zip(labels, calendar_ids):
            calendar = calendars.get(calendar_id)
            if calendar is None or calendar.get("errors") or not isinstance(calendar.get("busy"), list):
                unknown += 1
                reasons = {error.get("reason") for error in (calendar or {}).get("errors", [])}
                reason = "not_found_or_not_shared" if "notFound" in reasons else "access_denied" if "forbidden" in reasons else "provider_unavailable"
                checks.append({"calendar": label, "status": "unknown", "busy_count": None, "reason": reason})
                continue
            check = {"calendar": label, "status": "checked", "busy_count": len(calendar["busy"])}
            if calendar_id != label:
                check["shared_calendar"] = True
            checks.append(check)
            # Keep only the two fields needed by the scheduler.
            busy.extend({"start": item["start"], "end": item["end"]} for item in calendar["busy"])
        if (not calendars.get("primary") or calendars["primary"].get("errors")
                or not isinstance(calendars["primary"].get("busy"), list)):
            raise CalendarError("Your own calendar availability could not be checked.")
        return {"busy": busy, "unknown": unknown, "checks": checks}

    def create(self, owner, draft_id, meeting, slot):
        """Called only by the backend after approval, never exposed as an agent tool."""
        payload = {
            "id": draft_id, "summary": meeting["title"],
            "description": escape(f"Purpose: {meeting['purpose']}\n\nAgenda:\n{meeting['agenda']}"),
            "start": {"dateTime": slot["start"], "timeZone": meeting["timezone"]},
            "end": {"dateTime": slot["end"], "timeZone": meeting["timezone"]},
            "attendees": [{"email": email} for email in meeting["attendees"]],
            "visibility": "private", "guestsCanSeeOtherGuests": False,
            "guestsCanInviteOthers": False, "guestsCanModify": False,
            "extendedProperties": {"private": {"meetingAssistantDraft": draft_id}},
        }
        with self._session(owner, True) as client:
            response = client.post(f"{BASE}/calendars/primary/events", params={"sendUpdates": "all"},
                                   json=payload, timeout=15)
        if response.status_code == 409:
            existing = self.lookup(owner, draft_id)
            if existing:
                return existing
            raise BookingUncertain("Google returned an event ID conflict. Check the operation status.", "id_conflict")
        if response.status_code >= 500:
            raise BookingUncertain("Google did not confirm creation. Check the operation status before retrying.", "provider_uncertain")
        if response.status_code not in (200, 201):
            raise availability_error(response)
        # Google's response may contain attendee details. Return only our reference.
        return self.event_reference(response.json(), draft_id, require_marker=False)

    def lookup(self, owner, draft_id):
        """Only read our own generated event ID, with minimal response fields."""
        with self._session(owner, True) as client:
            response = client.get(f"{BASE}/calendars/primary/events/{draft_id}",
                                  params={"fields": "id,htmlLink,status,extendedProperties"}, timeout=15)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise availability_error(response)
        return self.event_reference(response.json(), draft_id, require_marker=True)

    @staticmethod
    def event_reference(event, draft_id, require_marker):
        marker = event.get("extendedProperties", {}).get("private", {}).get("meetingAssistantDraft")
        if event.get("id") != draft_id or (require_marker and marker != draft_id):
            raise BookingUncertain("Google returned an unexpected event reference. Check status before retrying.", "unexpected_event")
        url = event.get("htmlLink", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.google.com", "calendar.google.com"}:
            url = ""
        return {"id": draft_id, "url": url, "cancelled": event.get("status") == "cancelled"}

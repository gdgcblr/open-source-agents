import pytest
from conftest import FakeResponse, FakeSession

from good_first_issue_agent.errors import AuthError, InvalidInputError, NotFoundError
from good_first_issue_agent.sentry_client import (
    ErrorTrackerClient,
    make_tracker_ref,
    parse_event,
    parse_issue_id,
)


def tracker_issue(i=1, **extra):
    data = {
        "id": str(1000 + i),
        "shortId": f"WEB-{i}",
        "title": f"TypeError: cannot read property 'name' of undefined ({i})",
        "culprit": "app/components/Profile.tsx in render",
        "permalink": f"https://sentry.io/organizations/acme/issues/{1000 + i}/",
        "level": "error",
        "status": "unresolved",
        "count": "42",
        "userCount": 3,
        "numComments": 0,
        "firstSeen": "2026-10-01T00:00:00Z",
        "lastSeen": "2026-10-20T00:00:00Z",
        "assignedTo": None,
        "metadata": {"type": "TypeError", "value": "cannot read property 'name' of undefined",
                     "filename": "app/components/Profile.tsx", "function": "render"},
        "project": {"slug": "web"},
    }
    data.update(extra)
    return data


def sentry(session, kind="sentry", base=None):
    ref = make_tracker_ref(kind, base, "acme", "web")
    return ErrorTrackerClient(ref, token="sntrys_token_value", session=session)


# --- configuration ---------------------------------------------------------------
def test_defaults_and_url_normalization():
    assert make_tracker_ref("sentry", None, "acme", "web").base_url == "https://sentry.io"
    assert make_tracker_ref("glitchtip", None, "acme", "web").base_url == "https://app.glitchtip.com"
    ref = make_tracker_ref("glitchtip", "https://gt.example.com/api/0/", "acme", "web")
    assert ref.base_url == "https://gt.example.com"
    assert make_tracker_ref("glitchtip", "http://localhost:8000", "a", "b").base_url == "http://localhost:8000"


@pytest.mark.parametrize("base, org, project", [
    (None, None, "web"),
    (None, "acme", ""),
    (None, "acme/../x", "web"),
    (None, "acme", "web project"),
    ("http://gt.example.com", "acme", "web"),  # token over plain http
    ("ftp://gt.example.com", "acme", "web"),
    ("not a url", "acme", "web"),
])
def test_invalid_configuration(base, org, project):
    with pytest.raises(InvalidInputError):
        make_tracker_ref("glitchtip", base, org, project)


def test_token_is_required():
    ref = make_tracker_ref("sentry", None, "acme", "web")
    with pytest.raises(InvalidInputError, match="SENTRY_AUTH_TOKEN"):
        ErrorTrackerClient(ref, token=None)


@pytest.mark.parametrize("value", ["WEB-1A", "12a", "", "-5"])
def test_issue_id_must_be_numeric(value):
    with pytest.raises(InvalidInputError):
        parse_issue_id(value)


# --- listing ----------------------------------------------------------------------
def test_sentry_uses_org_endpoint_with_project_slug():
    session = FakeSession([FakeResponse(200, [tracker_issue(1)])])
    issues = sentry(session).list_issues(limit=5)
    call = session.calls[0]
    assert call["url"] == "https://sentry.io/api/0/organizations/acme/issues/"
    assert call["params"]["project"] == "web"
    assert call["params"]["query"] == "is:unresolved"
    assert call["headers"]["Authorization"] == "Bearer sntrys_token_value"
    i = issues[0]
    assert (i.source, i.display_id, i.event_count, i.user_count) == ("sentry", "WEB-1", 42, 3)
    assert i.stack_files == ["app/components/Profile.tsx"]


def test_glitchtip_uses_project_endpoint():
    session = FakeSession([FakeResponse(200, [tracker_issue(1)])])
    sentry(session, kind="glitchtip", base="https://gt.example.com").list_issues()
    assert session.calls[0]["url"] == "https://gt.example.com/api/0/projects/acme/web/issues/"


def test_personal_data_is_masked_on_ingest():
    raw = tracker_issue(1, title="Login failed for jane@example.com from 10.1.2.3",
                        metadata={"type": "AuthError", "value": "token=abcdef123456 user bob@corp.io"})
    session = FakeSession([FakeResponse(200, [raw])])
    issue = sentry(session).list_issues()[0]
    assert "jane@example.com" not in issue.title and "10.1.2.3" not in issue.title
    assert "bob@corp.io" not in issue.body and "abcdef123456" not in issue.body


def test_pagination_follows_same_origin_only():
    next_ok = {"next": {"url": "https://sentry.io/api/0/organizations/acme/issues/?cursor=1", "results": "true"}}
    next_evil = {"next": {"url": "https://evil.example.com/steal", "results": "true"}}
    session = FakeSession([
        FakeResponse(200, [tracker_issue(1)], links=next_ok),
        FakeResponse(200, [tracker_issue(2)], links=next_evil),
    ])
    issues = sentry(session).list_issues(limit=10)
    assert len(issues) == 2
    assert all("evil" not in c["url"] for c in session.calls)


def test_pagination_stops_when_no_more_results():
    links = {"next": {"url": "https://sentry.io/api/0/x?cursor=2", "results": "false"}}
    session = FakeSession([FakeResponse(200, [tracker_issue(1)], links=links)])
    assert len(sentry(session).list_issues(limit=10)) == 1
    assert len(session.calls) == 1


def test_project_not_found_and_bad_token():
    with pytest.raises(NotFoundError, match="acme/web"):
        sentry(FakeSession([FakeResponse(404, {})])).list_issues()
    with pytest.raises(AuthError):
        sentry(FakeSession([FakeResponse(401, {})])).list_issues()


def test_bad_request_400_is_input_error():
    session = FakeSession([FakeResponse(400, {"detail": "Invalid query"})])
    with pytest.raises(InvalidInputError, match="Invalid query"):
        sentry(session).list_issues()


def test_get_issue_from_other_project_is_rejected():
    session = FakeSession([FakeResponse(200, tracker_issue(1, project={"slug": "billing"}))])
    with pytest.raises(InvalidInputError, match="billing"):
        sentry(session).get_issue("1001")


# --- events -------------------------------------------------------------------------
SENTRY_EVENT = {
    "platform": "javascript",
    "entries": [
        {"type": "breadcrumbs", "data": {"values": [{"message": "user clicked secret"}]}},
        {"type": "exception", "data": {"values": [{
            "type": "TypeError",
            "value": "x is undefined for alice@example.com",
            "stacktrace": {"frames": [
                {"filename": "node_modules/react-dom/index.js", "function": "commit", "lineNo": 10, "inApp": False},
                {"filename": "app/utils/format.ts", "function": "fmt", "lineNo": 12, "inApp": True,
                 "vars": {"password": "hunter2"}},
                {"filename": "app/components/Profile.tsx", "function": "render", "lineNo": 40, "inApp": True,
                 "context": [[40, "const apiKey = 'AIzaSyD-secret'"]]},
            ]},
        }]}},
    ],
    "tags": [{"key": "environment", "value": "production"}],
}


def test_parse_event_prefers_app_frames_innermost_first_and_drops_sensitive_data():
    event = parse_event(SENTRY_EVENT)
    files = [f["file"] for f in event["frames"]]
    assert files == ["app/components/Profile.tsx", "app/utils/format.ts"]
    assert event["environment"] == "production"
    dumped = str(event)
    assert "hunter2" not in dumped and "AIzaSy" not in dumped and "user clicked" not in dumped
    assert "alice@example.com" not in dumped


def test_parse_event_glitchtip_style_top_level_exception():
    data = {"exception": {"values": [{"type": "KeyError", "value": "'id'", "stacktrace": {"frames": [
        {"filename": "api/views.py", "function": "get", "lineno": 7, "in_app": True}]}}]}}
    event = parse_event(data)
    assert event["frames"][0] == {"file": "api/views.py", "function": "get", "line": 7, "in_app": True}


def test_parse_event_handles_missing_data():
    assert parse_event({})["frames"] == []
    assert parse_event({"entries": [{"type": "exception", "data": None}]})["exceptions"] == []

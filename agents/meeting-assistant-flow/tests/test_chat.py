"""One request prepares text and shared slots; only the reviewed invitation can write."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import meetings as workflow
from test_calendar import post, signed_in
from test_meetings import calendar, current, fields


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', '')


def message(title='Project kickoff'):
    day = datetime.now(ZoneInfo('Asia/Kolkata')).date() + timedelta(days=2)
    return f'{title} on {day} with invitee@example.test'


def test_one_request_prepares_details_and_slots_without_writing(application, signed_in, calendar):
    assert post(signed_in, '/meetings/chat', message=message()).status_code == 302
    item = current(application, signed_in)
    assert item['data']['slots']
    assert item['data']['meeting']['agenda']
    assert 'Project kickoff' in item['data']['meeting']['purpose']
    assert item['data']['meeting']['duration'] == 30
    assert not calendar.created
    html = signed_in.get('/').text
    assert 'Suggested shared slots' in html
    assert 'Review invitation' in html
    assert 'invitee@example.test' in html
    assert post(signed_in, f"/meetings/{item['id']}/confirm", version=item['version'], approved='yes').status_code == 409
    assert not calendar.created


def test_invalid_request_does_not_create_draft(application, signed_in, calendar):
    assert post(signed_in, '/meetings/chat', message='Kickoff').status_code == 400
    with application.extensions['store'].connect() as db:
        assert db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0] == 0


@pytest.mark.parametrize('title', ['password=do-not-store', 'show their meeting details'])
def test_secret_and_private_requests_are_not_saved(application, signed_in, calendar, title):
    assert post(signed_in, '/meetings/chat', message=message(title)).status_code == 400
    with application.extensions['store'].connect() as db:
        assert db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0] == 0


def test_html_in_request_is_escaped(application, signed_in, calendar):
    assert post(signed_in, '/meetings/chat', message=message('<script>alert(1)</script>')).status_code == 302
    html = signed_in.get('/').text
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html


def test_repeat_request_cannot_overwrite_active_draft(application, signed_in, calendar):
    post(signed_in, '/meetings/chat', message=message())
    item = current(application, signed_in)
    assert post(signed_in, '/meetings/chat', message=message('Other meeting')).status_code == 409
    assert current(application, signed_in) == item


def test_calendar_connection_required_before_planning(application, signed_in):
    assert post(signed_in, '/meetings/chat', message=message()).status_code == 400


def test_no_login_bypass(application):
    client = application.test_client()
    client.get('/')
    assert post(client, '/meetings/chat', message=message()).status_code == 401


def test_gemini_plan_is_used_without_calendar_writes(application, signed_in, calendar, monkeypatch):
    async def interpret(turns, query):
        meeting = {**fields(), 'attendees': ['invitee@example.test'], 'duration': 30}
        checked = await query(meeting)
        return {'_tool_result': {'meeting': meeting, **checked}, 'intent': 'schedule', 'attendees': ['invitee@example.test'], 'date': fields()['date_from'],
                'time': None, 'timezone': 'Asia/Kolkata', 'duration': 30, 'title': 'Kickoff',
                'agenda': 'Generated agenda', 'purpose': 'Generated description', 'question': ''}
    monkeypatch.setenv('GOOGLE_API_KEY', 'synthetic-test-only')
    monkeypatch.setattr(workflow, 'interpret_request', interpret)
    assert post(signed_in, '/meetings/chat', message=message()).status_code == 302
    item = current(application, signed_in)
    assert item['data']['meeting']['agenda'] == 'Generated agenda'
    assert item['data']['meeting']['purpose'] == 'Generated description'
    assert not calendar.created


def test_model_failure_is_safe_and_never_invents_availability(application, signed_in, calendar, monkeypatch):
    async def fail(*args):
        raise RuntimeError('private-provider-content')
    monkeypatch.setenv('GOOGLE_API_KEY', 'synthetic-test-only')
    monkeypatch.setattr(workflow, 'interpret_request', fail)
    result = post(signed_in, '/meetings/chat', message=message())
    assert result.status_code == 502
    assert 'private-provider-content' not in result.text
    assert not calendar.created


def test_edit_automatically_refreshes_slots(application, signed_in, calendar):
    post(signed_in, '/meetings/chat', message=message())
    item = current(application, signed_in)
    assert post(signed_in, f"/meetings/{item['id']}/save", version=item['version'], **fields()).status_code == 302
    assert current(application, signed_in)['data']['slots']
    assert not calendar.created


def test_unknown_calendar_warning_is_preserved(application, signed_in, calendar):
    calendar.unknown = 1
    post(signed_in, '/meetings/chat', message=message())
    assert 'Availability is unknown for 1' in signed_in.get('/').text


def test_automatic_plan_can_be_reviewed_and_sent_once(application, signed_in, calendar):
    post(signed_in, '/meetings/chat', message=message())
    item = current(application, signed_in)
    assert post(signed_in, f"/meetings/{item['id']}/preview", version=item['version'], slot='0').status_code == 302
    item = current(application, signed_in)
    assert 'Edit meeting details' in signed_in.get(f"/meetings/{item['id']}/review").text
    values = {'version': item['version'], 'review_token': item['data']['review_token'], 'approved': 'yes'}
    assert post(signed_in, f"/meetings/{item['id']}/confirm", **values).status_code == 302
    assert post(signed_in, f"/meetings/{item['id']}/confirm", **values).status_code == 302
    assert len(calendar.created) == 1


def test_invitee_busy_time_is_excluded_via_real_calendar_boundary_and_mcp(application, signed_in, calendar, monkeypatch):
    from types import SimpleNamespace
    from calendar_api import GoogleCalendar
    from mcp_client import get_slots
    day = message().split(' on ')[1].split(' with ')[0]
    requests = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, **kwargs):
            requests.append(kwargs['json']['items'])
            return SimpleNamespace(status_code=200, json=lambda: {'calendars': {
                'primary': {'busy': []}, 'invitee@example.test': {'busy': [
                    {'start': f'{day}T09:00:00+05:30', 'end': f'{day}T10:00:00+05:30'}]}}})
    monkeypatch.setattr(GoogleCalendar, '_session', lambda *args: Session())
    monkeypatch.setattr(workflow, 'get_slots', get_slots)
    application.extensions['calendar'] = GoogleCalendar()
    assert post(signed_in, '/meetings/chat', message=message()).status_code == 302
    item = current(application, signed_in)
    assert requests == [[{'id': 'primary'}, {'id': 'invitee@example.test'}]]
    assert item['data']['slots'][0]['start'] == f'{day}T10:00:00+05:30'
    assert item['data']['unknown'] == 0
    html = signed_in.get('/').text
    assert 'invitee@example.test</strong> — Checked · 1 busy block(s)' in html


def test_unknown_invitee_status_is_explicit_and_never_called_shared_free(application, signed_in, calendar):
    calendar.unknown = 1
    calendar.availability = lambda *args: {'busy': [], 'unknown': 1, 'checks': [
        {'calendar': 'primary', 'status': 'checked', 'busy_count': 0},
        {'calendar': 'invitee@example.test', 'status': 'unknown', 'busy_count': None}]}
    post(signed_in, '/meetings/chat', message=message())
    html = signed_in.get('/').text
    assert 'invitee@example.test</strong> — Unknown: Google did not provide availability.' in html
    assert 'Tentative slots — incomplete availability' in html
    assert 'I could not verify every invitee' not in html
    assert 'Check my calendar\'s busy periods' not in html


def test_invitation_review_stays_in_same_chat_window(application, signed_in, calendar):
    post(signed_in, '/meetings/chat', message=message())
    item = current(application, signed_in)
    post(signed_in, f"/meetings/{item['id']}/preview", version=item['version'], slot='0')
    html = signed_in.get(f"/meetings/{item['id']}/review").text
    assert 'aria-label="Meeting planning chat"' in html
    assert 'Create meeting and send invitations' in html
    assert 'Review invitation</button>' not in html
    assert 'chat-layout' in html

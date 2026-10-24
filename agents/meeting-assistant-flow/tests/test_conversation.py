"""Natural chat uses verified tool results, never model claims, to offer bookings."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import meetings as workflow
from test_calendar import signed_in, post
from test_meetings import calendar, current


def plan(**changes):
    return {'intent': 'check_time', 'attendees': ['invitee@example.test'],
            'date': str(datetime.now(ZoneInfo('Asia/Kolkata')).date() + timedelta(days=2)),
            'time': '15:00', 'timezone': 'Asia/Kolkata', 'duration': 30,
            'title': 'Project call', 'purpose': 'Discuss project scope', 'agenda': 'Goals and next steps',
            'question': '', **changes}


def interpreter(monkeypatch, result, call_tool=True):
    monkeypatch.setenv('GOOGLE_API_KEY', 'synthetic-test-only')
    async def interpret(turns, query):
        value = dict(result)
        if call_tool and value['date'] and value['attendees'] and not value['question']:
            meeting = {'title': 'Availability check', 'purpose': '', 'agenda': '', 'attendees': value['attendees'],
                       'date_from': value['date'], 'date_to': value['date'], 'timezone': value['timezone'],
                       'duration': value['duration'], 'hour_start': 9, 'hour_end': 17, 'include_weekends': True}
            value['_tool_result'] = {'meeting': meeting, **await query(meeting)}
        return value
    monkeypatch.setattr(workflow, 'interpret_request', interpret)


def test_specific_time_check_replies_from_tool_without_sending(application, signed_in, calendar, monkeypatch):
    interpreter(monkeypatch, plan())
    assert post(signed_in, '/meetings/chat', message='Is Alex available at 3 PM?').status_code == 302
    item = current(application, signed_in)
    assert 'free for the requested time' in item['data']['messages'][-1]['text']
    assert not item['data'].get('selected')
    assert not calendar.created


def test_scheduling_free_exact_time_prepares_approval(application, signed_in, calendar, monkeypatch):
    interpreter(monkeypatch, plan(intent='schedule'))
    post(signed_in, '/meetings/chat', message='Schedule a call at 3 PM')
    item = current(application, signed_in)
    assert item['status'] == 'ready'
    assert 'T15:00:' in item['data']['selected']['start']
    assert 'Create meeting and send invitations' in signed_in.get('/').text
    assert not calendar.created


def test_conflict_prevents_exact_time_approval(application, signed_in, calendar, monkeypatch):
    value = plan(intent='schedule')
    calendar.busy = [{'start': value['date']+'T15:00:00+05:30', 'end': value['date']+'T16:00:00+05:30'}]
    interpreter(monkeypatch, value)
    post(signed_in, '/meetings/chat', message='Schedule at 3 PM')
    item = current(application, signed_in)
    assert item['status'] == 'draft'
    assert 'conflicts' in item['data']['messages'][-1]['text']
    assert not calendar.created


def test_unknown_is_never_reported_as_free(application, signed_in, calendar, monkeypatch):
    calendar.unknown = 1
    interpreter(monkeypatch, plan(intent='schedule'))
    post(signed_in, '/meetings/chat', message='Schedule at 3 PM')
    item = current(application, signed_in)
    assert item['status'] == 'draft'
    assert 'cannot confirm' in item['data']['messages'][-1]['text']
    assert not calendar.created


def test_missing_details_asks_followup_and_retains_context(application, signed_in, calendar, monkeypatch):
    interpreter(monkeypatch, plan(attendees=[], question='What is Alex’s email?'), call_tool=False)
    post(signed_in, '/meetings/chat', message='Is Alex available at 3 PM?')
    item = current(application, signed_in)
    assert 'Alex' in item['data']['messages'][-1]['text']
    assert 'slots' not in item['data']
    interpreter(monkeypatch, plan())
    assert post(signed_in, '/meetings/chat', version=item['version'], message='alex is invitee@example.test').status_code == 302
    assert len(current(application, signed_in)['data']['messages']) == 4


def test_model_without_matching_tool_check_cannot_offer_booking(application, signed_in, calendar, monkeypatch):
    interpreter(monkeypatch, plan(intent='schedule'), call_tool=False)
    assert post(signed_in, '/meetings/chat', message='Schedule a call').status_code == 502
    assert not calendar.created


def test_reset_forgets_chat_and_invitees_but_keeps_login_and_calendar(application, signed_in, calendar, monkeypatch):
    interpreter(monkeypatch, plan())
    post(signed_in, '/meetings/chat', message='Is invitee@example.test free?')
    item = current(application, signed_in)
    assert post(signed_in, '/meetings/reset').status_code == 302
    html = signed_in.get('/').text
    assert 'invitee@example.test' not in html
    assert 'Your recent meetings' not in html
    with signed_in.session_transaction() as cookie:
        assert 'draft_id' not in cookie
        assert cookie['login']
    owner = signed_in.get('/api/me').json['user']['id']
    assert application.extensions['store'].calendar_connected(owner)
    with pytest.raises(LookupError):
        application.extensions['store'].get(item['id'], owner)

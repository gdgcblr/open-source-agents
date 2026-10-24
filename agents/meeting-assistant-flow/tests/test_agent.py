import asyncio
import json

import pytest

from agent import prepare_agenda


def test_missing_key_has_manual_agenda_fallback(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    meeting = {"title": "Kickoff", "purpose": "Plan scope", "agenda": "", "duration": 30}
    with pytest.raises(ValueError, match="enter|write your agenda manually"):
        asyncio.run(prepare_agenda(meeting, "Prepare an agenda"))


def test_real_adk_runner_with_offline_model(monkeypatch):
    from google.adk.agents import LlmAgent
    import google.adk.agents
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    seen = []
    class OfflineModel(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            seen.append(str(llm_request.contents))
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps({
                "title": "Project kickoff", "agenda": "Goals — 10 min\nScope — 15 min\nNext steps — 5 min", "reply": "Your agenda is ready for review."}))]))

    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-test-only")
    monkeypatch.setattr(google.adk.agents, "LlmAgent", lambda **kwargs: LlmAgent(**{**kwargs, "model": OfflineModel(model="offline-test")}))
    result = asyncio.run(prepare_agenda({"title": "Kickoff", "purpose": "Plan scope",
                                        "agenda": "", "duration": 30, "attendees": ["private@example.test"]}, "Prepare an agenda"))
    assert result["title"] == "Project kickoff"
    assert len(seen) == 1
    assert "private@example.test" not in seen[0]


def test_gemini_adk_calls_scheduling_tool_and_keeps_emails_local(monkeypatch):
    from google.adk.agents import LlmAgent
    import google.adk.agents
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
    from agent import interpret_request
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    day = str(datetime.now(ZoneInfo('Asia/Kolkata')).date() + timedelta(days=2))
    seen, queried = [], []
    class ToolModel(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            seen.append(str(llm_request.contents))
            if len(seen) == 1:
                part = types.Part(function_call=types.FunctionCall(name='check_calendar_availability', args={
                    'attendees': ['attendee_1'], 'date': day, 'timezone': 'Asia/Kolkata', 'duration': 30}))
            else:
                part = types.Part(text=json.dumps({'intent': 'check_time', 'attendees': ['attendee_1'],
                    'date': day, 'time': '15:00', 'title': 'Call', 'purpose': '', 'agenda': '', 'question': ''}))
            yield LlmResponse(content=types.Content(role='model', parts=[part]))
    monkeypatch.setenv('GOOGLE_API_KEY', 'synthetic-test-only')
    monkeypatch.setattr(google.adk.agents, 'LlmAgent', lambda **kwargs: LlmAgent(**{**kwargs, 'model': ToolModel(model='offline-tool-test')}))
    async def query(meeting):
        queried.append(meeting)
        return {'result': {'busy': [], 'unknown': 0, 'checks': [
            {'calendar': 'private@example.test', 'status': 'checked', 'busy_count': 0}]}, 'slots': []}
    result = asyncio.run(interpret_request([{'role': 'user', 'text': f'Is private@example.test free on {day} at 3 PM?'}], query))
    assert len(queried) == 1
    assert queried[0]['attendees'] == ['private@example.test']
    assert len(seen) == 2
    assert all('private@example.test' not in payload for payload in seen)
    assert result['attendees'] == ['private@example.test']
    assert result['_tool_result']['result']['unknown'] == 0

import asyncio
import base64
import json
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.main import create_app
from app.security import create_stream_token
from app.services import voice_agent
from app.services.voice_agent import build_agent_settings
from tests.conftest import DASHBOARD_AUTH, TWILIO_AUTH_TOKEN, make_settings, signed_twilio_post

CALL_SID = "CA00000000000000000000000000000002"
STREAM_SID = "MZ00000000000000000000000000000002"
CALLER = "+919811122233"
AGENT_AUDIO = b"\xff" * 320
GREETING = "Hello, welcome to Test General Hospital."
QUESTION = "When does Dr. Asha Rao see patients?"


class FakeAgent:
    """Stands in for the Deepgram Voice Agent WebSocket with a scripted list of events.

    `replies` maps a message type the bridge sends to the events Deepgram would answer with.
    """

    def __init__(
        self, events: list[str | bytes], replies: dict[str, list[str | bytes]] | None = None
    ) -> None:
        self.sent: list[str | bytes] = []
        self._queue: asyncio.Queue[str | bytes] = asyncio.Queue()
        for event in events:
            self._queue.put_nowait(event)
        self._replies = replies or {}

    async def __aenter__(self) -> "FakeAgent":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)
        if isinstance(message, str):
            for event in self._replies.get(json.loads(message)["type"], []):
                self._queue.put_nowait(event)

    def __aiter__(self) -> Any:
        return self._stream()

    async def _stream(self) -> Any:
        while True:  # stay connected until the caller hangs up
            yield await self._queue.get()

    def json_messages(self) -> list[dict[str, Any]]:
        return [json.loads(m) for m in self.sent if isinstance(m, str)]


def _start_event(token: str) -> dict[str, Any]:
    return {
        "event": "start",
        "streamSid": STREAM_SID,
        "start": {
            "streamSid": STREAM_SID,
            "callSid": CALL_SID,
            "customParameters": {"token": token},
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
        },
    }


def _media_event(payload: bytes) -> dict[str, Any]:
    return {
        "event": "media",
        "streamSid": STREAM_SID,
        "media": {"track": "inbound", "payload": base64.b64encode(payload).decode()},
    }


def _next_weekday(weekday: int) -> date:
    """The next date strictly after today (hospital time) that falls on `weekday`."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return today + timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


def _fake_clock(*readings: float) -> Iterator[float]:
    return iter(readings)


def _run_call(client: TestClient, monkeypatch: pytest.MonkeyPatch, agent: FakeAgent) -> list[dict]:
    """Drive one media stream until the agent's audio arrives, then hang up."""
    monkeypatch.setattr(voice_agent, "connect_to_agent", lambda api_key: agent)
    received: list[dict] = []
    with client.websocket_connect("/api/twilio/media-stream") as ws:
        ws.send_json({"event": "connected", "protocol": "Call", "version": "1.0.0"})
        ws.send_json(_start_event(create_stream_token(CALL_SID, TWILIO_AUTH_TOKEN)))
        for _ in range(5):  # five 20 ms frames = one 100 ms chunk for Deepgram
            ws.send_json(_media_event(b"\x7f" * 160))
        while not received or received[-1]["event"] != "media":
            received.append(ws.receive_json())
        ws.send_json({"event": "stop", "streamSid": STREAM_SID, "stop": {"callSid": CALL_SID}})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    return received


@pytest.fixture(autouse=True)
def no_real_recordings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    started: list[str] = []

    async def fake_start_recording(settings: Settings, call_sid: str) -> str:
        started.append(call_sid)
        return "RE0002"

    monkeypatch.setattr(voice_agent, "start_call_recording", fake_start_recording)
    return started


def test_agent_settings_match_twilio_audio_format(settings: Settings) -> None:
    agent_settings = build_agent_settings(settings, prompt="Be helpful.", greeting="Hello!")

    assert agent_settings["audio"]["input"] == {"encoding": "mulaw", "sample_rate": 8000}
    assert agent_settings["audio"]["output"]["container"] == "none"
    assert agent_settings["agent"]["listen"]["provider"]["version"] == "v2"
    think = agent_settings["agent"]["think"]
    assert think["provider"] == {"type": "anthropic", "model": "claude-sonnet-5"}
    assert think["prompt"] == "Be helpful."
    assert [f["name"] for f in think["functions"]] == [
        "set_language",
        "find_slot",
        "book_appointment",
        "find_appointments",
        "cancel_appointment",
    ]
    # Flux Multilingual, biased toward English and Hindi; the call opens with the English voice.
    assert agent_settings["agent"]["listen"]["provider"] == {
        "type": "deepgram",
        "version": "v2",
        "model": "flux-general-multi",
        "language_hints": ["en", "hi"],
    }
    assert agent_settings["agent"]["speak"]["provider"]["model"] == "flux-priya-en"
    assert agent_settings["agent"]["greeting"] == "Hello!"


def test_non_flux_models_use_the_v1_api(settings: Settings) -> None:
    nova = settings.model_copy(
        update={"deepgram_listen_model": "nova-3", "deepgram_speak_model": "aura-2-thalia-en"}
    )

    agent = build_agent_settings(nova, prompt="unused", greeting="unused")["agent"]

    assert agent["listen"]["provider"]["version"] == "v1"
    assert "language_hints" not in agent["listen"]["provider"]  # only Flux Multilingual takes them
    assert agent["speak"]["provider"]["version"] == "v1"


def test_media_stream_relays_audio_saves_the_conversation_and_prices_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, no_real_recordings: list[str]
) -> None:
    monkeypatch.setattr(voice_agent, "session_clock", _fake_clock(1000.0, 1090.0).__next__)
    agent = FakeAgent(
        [
            json.dumps({"type": "Welcome", "request_id": "req-1"}),
            json.dumps({"type": "ConversationText", "role": "assistant", "content": GREETING}),
            json.dumps({"type": "ConversationText", "role": "user", "content": QUESTION}),
            json.dumps({"type": "UserStartedSpeaking"}),
            AGENT_AUDIO,
        ]
    )

    received = _run_call(client, monkeypatch, agent)

    assert received == [
        {"event": "clear", "streamSid": STREAM_SID},
        {
            "event": "media",
            "streamSid": STREAM_SID,
            "media": {"payload": base64.b64encode(AGENT_AUDIO).decode()},
        },
    ]
    agent_config = json.loads(agent.sent[0])
    assert agent_config["type"] == "Settings"
    assert agent_config["agent"]["greeting"].startswith(GREETING)
    assert "| Dr. Asha Rao | Cardiology |" in agent_config["agent"]["think"]["prompt"]
    assert agent.sent[1] == b"\x7f" * 800
    assert no_real_recordings == [CALL_SID]

    [call] = client.get("/api/calls").json()["items"]
    detail = client.get(f"/api/calls/{call['id']}").json()
    assert detail["status"] == "completed"
    assert [(t["role"], t["text"]) for t in detail["turns"]] == [
        ("agent", GREETING),
        ("customer", QUESTION),
    ]
    # 90 seconds of agent time at the default $0.163 per minute.
    assert detail["agent_seconds"] == 90.0
    assert detail["agent_cost_usd"] == 0.2445
    assert detail["total_cost_usd"] == 0.2445


def _function_call(call_id: str, name: str, **arguments: object) -> str:
    return json.dumps(
        {
            "type": "FunctionCallRequest",
            "functions": [
                {
                    "id": call_id,
                    "name": name,
                    "arguments": json.dumps(arguments),
                    "client_side": True,
                }
            ],
        }
    )


def test_receptionist_books_an_appointment_during_the_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Next Monday at 8 AM in Pune: Dr. Asha Rao's first slot that day is free and within 72 hours.
    monday = _next_weekday(0)
    monday_8am = datetime.combine(monday, time(8, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(voice_agent, "wall_clock", lambda tz: monday_8am)
    answered = signed_twilio_post(
        client, "/api/twilio/voice", {"CallSid": CALL_SID, "From": CALLER}
    )
    assert answered.status_code == 200
    agent = FakeAgent(
        [
            _function_call("fc_lang", "set_language", language="en"),
            _function_call("fc_slot", "find_slot", doctor_name="Asha Rao"),
            _function_call(
                "fc_book",
                "book_appointment",
                doctor_name="Dr. Asha Rao",
                date=monday.isoformat(),
                time="09:00",
                patient_name="Ravi Kumar",
                patient_age=42,
                patient_gender="male",
                patient_phone=CALLER,
                symptoms="Chest tightness when climbing stairs",
                caller_confirmed=True,
            ),
            AGENT_AUDIO,
        ]
    )

    _run_call(client, monkeypatch, agent)

    language, slot, book = [m for m in agent.json_messages() if m["type"] == "FunctionCallResponse"]
    assert json.loads(language["content"])["language"] == "en"
    assert (slot["id"], slot["name"]) == ("fc_slot", "find_slot")
    assert json.loads(slot["content"])["time"] == "09:00"
    assert (book["id"], book["name"]) == ("fc_book", "book_appointment")
    booking = json.loads(book["content"])
    assert booking["status"] == "booked"

    [call] = client.get("/api/calls").json()["items"]
    [appointment] = client.get(f"/api/calls/{call['id']}").json()["appointments"]
    assert appointment["reference"] == booking["reference"]
    assert appointment["doctor_name"] == "Dr. Asha Rao"
    assert appointment["appointment_date"] == monday.isoformat()
    assert appointment["start_time"] == "09:00:00"
    assert (appointment["patient_age"], appointment["patient_gender"]) == (42, "male")
    assert appointment["symptoms"] == "Chest tightness when climbing stairs"

    upcoming = client.get("/api/appointments").json()["items"]
    assert [a["reference"] for a in upcoming] == [booking["reference"]]

    events = client.get(f"/api/calls/{call['id']}").json()["events"]
    types = [e["type"] for e in events]
    # Recording starts in the background, so it may land before or after the agent answers.
    assert sorted(types[:2]) == ["call_started", "recording_started"]
    assert types[2:] == [
        "language_changed",
        "availability_checked",
        "appointment_booked",
        "call_ended",
    ]
    assert events[4]["message"].startswith(f"Booked {booking['reference']}: Dr. Asha Rao")


def test_receptionist_hangs_up_after_three_unsupported_languages(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    hung_up: list[str] = []

    async def fake_end_call(settings: Settings, call_sid: str) -> None:
        hung_up.append(call_sid)

    monkeypatch.setattr(voice_agent, "end_call", fake_end_call)
    goodbye = [AGENT_AUDIO, json.dumps({"type": "AgentAudioDone"})]
    agent = FakeAgent(
        [
            _function_call("fc_1", "set_language", language="ta"),
            _function_call("fc_2", "set_language", language="unknown"),
            _function_call("fc_3", "set_language", language="fr"),
        ],
        # After each result the agent speaks: asking again twice, then its goodbye.
        replies={"FunctionCallResponse": goodbye},
    )
    monkeypatch.setattr(voice_agent, "connect_to_agent", lambda api_key: agent)

    with client.websocket_connect("/api/twilio/media-stream") as ws:
        ws.send_json(_start_event(create_stream_token(CALL_SID, TWILIO_AUTH_TOKEN)))
        received = ws.receive_json()
        while received["event"] != "mark":  # the replies' audio, then the goodbye's mark
            received = ws.receive_json()
        ws.send_json({"event": "mark", "streamSid": STREAM_SID, "mark": {"name": "goodbye"}})
        with pytest.raises(WebSocketDisconnect):
            while True:  # the fake agent may still have audio queued when the bridge hangs up
                ws.receive_json()

    statuses = [
        json.loads(m["content"])["status"]
        for m in agent.json_messages()
        if m["type"] == "FunctionCallResponse"
    ]
    assert statuses == ["not_supported", "not_supported", "ending_call"]
    assert hung_up == [CALL_SID]
    [call] = client.get("/api/calls").json()["items"]
    events = client.get(f"/api/calls/{call['id']}").json()["events"]
    assert (
        "agent_ended_call",
        "Ending the call: the caller didn't choose English or Hindi after 3 tries",
    ) in [(e["type"], e["message"]) for e in events]


def test_receptionist_switches_to_the_hindi_voice(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = FakeAgent(
        [
            json.dumps(
                {
                    "type": "FunctionCallRequest",
                    "functions": [
                        {
                            "id": "fc_lang",
                            "name": "set_language",
                            "arguments": json.dumps({"language": "hi"}),
                            "client_side": True,
                        }
                    ],
                }
            ),
            json.dumps({"type": "ConversationText", "role": "assistant", "content": "जी, बताइए।"}),
            AGENT_AUDIO,
        ]
    )

    _run_call(client, monkeypatch, agent)

    messages = [m for m in agent.json_messages() if m["type"] != "Settings"]
    # The voice changes before the function result, so the Hindi reply uses the Hindi voice.
    assert [m["type"] for m in messages] == ["UpdateSpeak", "FunctionCallResponse"]
    assert messages[0]["speak"]["provider"] == {
        "type": "deepgram",
        "version": "v2",
        "model": "flux-anjali-hi",
    }
    assert json.loads(messages[1]["content"])["language"] == "hi"

    [call] = client.get("/api/calls").json()["items"]
    detail = client.get(f"/api/calls/{call['id']}").json()
    assert detail["language"] == "hi"
    assert ("language_changed", "Switched to Hindi") in [
        (e["type"], e["message"]) for e in detail["events"]
    ]
    assert detail["turns"][-1]["text"] == "जी, बताइए।"


def test_server_side_function_calls_are_left_to_deepgram(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = FakeAgent(
        [
            json.dumps(
                {
                    "type": "FunctionCallRequest",
                    "functions": [
                        {
                            "id": "fc_srv",
                            "name": "end_call",
                            "arguments": "{}",
                            "client_side": False,
                        }
                    ],
                }
            ),
            AGENT_AUDIO,
        ]
    )

    _run_call(client, monkeypatch, agent)

    assert not [m for m in agent.json_messages() if m["type"] == "FunctionCallResponse"]


def test_calls_end_with_a_goodbye_at_the_time_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hung_up: list[str] = []

    async def fake_end_call(settings: Settings, call_sid: str) -> None:
        hung_up.append(call_sid)

    monkeypatch.setattr(voice_agent, "end_call", fake_end_call)
    # Deepgram speaks the injected goodbye, then reports that its audio is done.
    agent = FakeAgent(
        [], replies={"InjectAgentMessage": [AGENT_AUDIO, json.dumps({"type": "AgentAudioDone"})]}
    )
    monkeypatch.setattr(voice_agent, "connect_to_agent", lambda api_key: agent)
    settings = make_settings(tmp_path, max_call_minutes=0.002)  # about 120 ms

    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect("/api/twilio/media-stream") as ws,
    ):
        ws.send_json(_start_event(create_stream_token(CALL_SID, TWILIO_AUTH_TOKEN)))
        assert ws.receive_json()["event"] == "media"  # the goodbye
        # Once the goodbye is queued, the bridge asks Twilio to report when it has played.
        assert ws.receive_json() == {
            "event": "mark",
            "mark": {"name": "goodbye"},
            "streamSid": STREAM_SID,
        }
        ws.send_json({"event": "mark", "streamSid": STREAM_SID, "mark": {"name": "goodbye"}})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

        client.auth = DASHBOARD_AUTH
        [call] = client.get("/api/calls").json()["items"]
        events = client.get(f"/api/calls/{call['id']}").json()["events"]

    inject = next(m for m in agent.json_messages() if m["type"] == "InjectAgentMessage")
    assert inject["behavior"] == "interrupt"
    assert inject["message"].startswith("I'm sorry, we've reached the time limit")
    assert hung_up == [CALL_SID]
    assert ("time_limit_reached", "Ended the call at the 0.002-minute limit") in [
        (e["type"], e["message"]) for e in events
    ]
    assert events[-1]["type"] == "call_ended"


@pytest.mark.parametrize(
    "first_message",
    [
        _start_event("forged-token"),
        {"event": "start", "start": {}},
        {"event": "start", "start": "not an object"},
        {"event": "connected", "protocol": "Call", "version": "1.0.0"},  # and then nothing
    ],
    ids=["forged token", "missing identifiers", "malformed start", "never starts"],
)
def test_media_stream_rejects_unauthenticated_streams(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, first_message: dict[str, Any]
) -> None:
    def fail_connect(api_key: str) -> FakeAgent:
        raise AssertionError("must not open a Deepgram session for an unauthenticated stream")

    monkeypatch.setattr(voice_agent, "connect_to_agent", fail_connect)
    monkeypatch.setattr(voice_agent, "STREAM_START_TIMEOUT_SECONDS", 0.1)

    with client.websocket_connect("/api/twilio/media-stream") as ws:
        ws.send_json(first_message)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()

    assert closed.value.code == 1008
    assert client.get("/api/calls").json()["total"] == 0

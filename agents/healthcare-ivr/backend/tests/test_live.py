import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SessionFactory, create_engine, create_session_factory, init_db
from app.main import create_app
from app.models import Call, CallSource, CallStatus, DiarizationStatus, SpeakerRole, TranscriptTurn
from app.routers.calls import stream_call
from app.services.events import LiveFeed
from tests.conftest import DASHBOARD_AUTH, make_settings, signed_twilio_post

CALL_SID = "CA00000000000000000000000000000003"


class _ConnectedRequest:
    """The bit of `Request` the stream uses: a viewer that stays connected."""

    async def is_disconnected(self) -> bool:
        return False


def _parse(chunk: str) -> dict:
    assert chunk.startswith("data: ")
    return json.loads(chunk.removeprefix("data: "))


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[SessionFactory]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'live.db'}")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _phone_call(session_factory: SessionFactory, status: CallStatus) -> str:
    async with session_factory() as db:
        call = Call(
            source=CallSource.PHONE,
            status=status,
            caller_number="+919811122233",
            diarization_status=DiarizationStatus.PENDING,
        )
        db.add(call)
        await db.commit()
        return call.id


@pytest.mark.anyio
async def test_feed_delivers_only_to_viewers_of_that_call() -> None:
    feed = LiveFeed()

    async with feed.subscribe("call-a") as watching_a, feed.subscribe("call-b") as watching_b:
        feed.publish("call-a", {"kind": "turn", "text": "Hello"})

        assert watching_a.get_nowait() == {"kind": "turn", "text": "Hello"}
        assert watching_b.empty()

    feed.publish("call-a", {"kind": "ended"})  # nobody watching: dropped quietly


@pytest.mark.anyio
async def test_feed_drops_updates_for_a_stalled_viewer() -> None:
    feed = LiveFeed(queue_size=1)

    async with feed.subscribe("call-a") as queue:
        feed.publish("call-a", {"kind": "turn", "text": "first"})
        feed.publish("call-a", {"kind": "turn", "text": "second"})

        assert queue.qsize() == 1


@pytest.mark.anyio
async def test_live_stream_relays_updates_until_the_call_ends(
    session_factory: SessionFactory,
) -> None:
    feed = LiveFeed()
    call_id = await _phone_call(session_factory, CallStatus.IN_PROGRESS)

    async with session_factory() as db:
        response = await stream_call(call_id, _ConnectedRequest(), db, feed)  # type: ignore[arg-type]
    updates = response.body_iterator

    assert _parse(await anext(updates)) == {"kind": "subscribed"}
    feed.publish(call_id, {"kind": "activity", "activity": "caller_speaking"})
    assert _parse(await anext(updates)) == {"kind": "activity", "activity": "caller_speaking"}
    feed.publish(call_id, {"kind": "ended"})
    assert _parse(await anext(updates)) == {"kind": "ended"}
    with pytest.raises(StopAsyncIteration):
        await anext(updates)


def test_stream_of_a_finished_call_ends_straight_away(client: TestClient) -> None:
    created = client.post(
        "/api/calls/upload", files={"file": ("call.wav", b"RIFF", "audio/wav")}
    ).json()

    response = client.get(f"/api/calls/{created['id']}/stream")

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == 'data: {"kind": "ended"}\n\n'


def test_live_calls_list_shows_the_latest_line(client: TestClient) -> None:
    signed_twilio_post(client, "/api/twilio/voice", {"CallSid": CALL_SID, "From": "+919811122233"})
    [call] = client.get("/api/calls").json()["items"]

    async def say(role: SpeakerRole, text: str) -> None:
        async with client.app.state.session_factory() as db:
            db.add(TranscriptTurn(call_id=call["id"], role=role, text=text))
            await db.commit()

    client.portal.call(say, SpeakerRole.AGENT, "Thank you for calling.")
    client.portal.call(say, SpeakerRole.CUSTOMER, "I'd like to see a cardiologist.")

    [live] = client.get("/api/calls/live").json()["items"]

    assert live["id"] == call["id"]
    assert live["caller_number"] == "+919811122233"
    assert live["latest_turn"]["role"] == "customer"
    assert live["latest_turn"]["text"] == "I'd like to see a cardiologist."


def test_calls_left_live_by_a_crash_are_closed_on_startup(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        signed_twilio_post(
            client, "/api/twilio/voice", {"CallSid": CALL_SID, "To": "+912012345678"}
        )
        assert len(client.get("/api/calls/live", auth=DASHBOARD_AUTH).json()["items"]) == 1

    with TestClient(create_app(settings)) as client:
        live = client.get("/api/calls/live", auth=DASHBOARD_AUTH).json()["items"]
        [call] = client.get("/api/calls", auth=DASHBOARD_AUTH).json()["items"]

    assert live == []
    assert call["status"] == "completed"
    assert call["called_number"] == "+912012345678"

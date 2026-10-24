"""Bridge between a Twilio Media Stream and a Deepgram Voice Agent session.

Twilio streams the caller's audio (8 kHz mu-law, base64 inside JSON frames) to our WebSocket.
We forward it to Deepgram's Voice Agent API, which runs speech-to-text, the LLM turn and
text-to-speech, and relay the agent's audio back to Twilio so the caller hears it. Each
finalized conversation turn is saved so the dashboard can show the live transcript.

The agent acts as the hospital's receptionist. Its prompt is rebuilt for every call from the
hospital directory, so edits apply from the next call. It books appointments through Deepgram
function calling: Deepgram sends a `FunctionCallRequest`, the bridge runs the matching tool and
answers with a `FunctionCallResponse`. The session's duration is recorded to estimate its cost.

Everything that happens is published to the live feed (transcript turns, timeline events, and
whether the caller or the receptionist is talking) so the dashboard can follow the call live.

The bridge also hangs up calls: when they reach `MAX_CALL_MINUTES` (with an injected goodbye),
and when a tool decides the call should end (the receptionist's next reply is its goodbye). Once
Twilio confirms the goodbye has played, the bridge hangs up through Twilio's REST API.
"""

import asyncio
import base64
import contextlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState
from twilio.base.exceptions import TwilioException
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from app.config import Settings
from app.db import SessionFactory
from app.models import Call, CallEventType, SpeakerRole, TranscriptTurn
from app.security import verify_stream_token
from app.services.calls import (
    get_or_create_phone_call,
    mark_call_completed,
    mark_diarization_failed,
    record_voice_agent_usage,
)
from app.services.costs import estimate_cost_usd
from app.services.events import LiveFeed, record_event
from app.services.hospital import HospitalDataError, build_receptionist_prompt, greeting_for
from app.services.hospital_store import load_hospital
from app.services.reception_tools import FUNCTION_DEFINITIONS, ToolContext, run_tool
from app.services.telephony import end_call, start_call_recording

logger = logging.getLogger(__name__)

DEEPGRAM_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
_MULAW_FRAME_BYTES = 160  # 20 ms of 8 kHz mu-law audio, the frame size Twilio sends
_AGENT_INPUT_CHUNK_BYTES = _MULAW_FRAME_BYTES * 5  # forward caller audio in 100 ms chunks
_ROLES = {"user": SpeakerRole.CUSTOMER, "assistant": SpeakerRole.AGENT}
# Deepgram events that say who is talking, relayed to live viewers but not stored.
_ACTIVITY = {
    "UserStartedSpeaking": "caller_speaking",
    "AgentThinking": "agent_thinking",
    "AgentStartedSpeaking": "agent_speaking",
    "AgentAudioDone": "listening",
}
# Said when a call reaches MAX_CALL_MINUTES, in the language the call is in.
_TIME_LIMIT_GOODBYES = {
    "en": (
        "I'm sorry, we've reached the time limit for this call. Please call again if you need "
        "anything else. Goodbye."
    ),
    "hi": "माफ़ कीजिए, इस कॉल का समय पूरा हो गया है। कुछ और चाहिए तो कृपया दोबारा कॉल करें। धन्यवाद।",
}
# Twilio sends `start` straight after connecting; anything slower isn't a real Twilio stream.
STREAM_START_TIMEOUT_SECONDS = 10
# Twilio echoes a named mark once all audio sent before it has played to the caller.
_GOODBYE_MARK = "goodbye"
_GOODBYE_PLAYBACK_TIMEOUT_SECONDS = 20

# Times the Deepgram session for cost estimates, and tells the tools the time. Tests
# substitute fakes for both.
session_clock = time.monotonic
wall_clock = datetime.now


def _provider_version(model: str) -> str:
    """Deepgram serves Flux models from its v2 API and Nova/Aura models from v1."""
    return "v2" if model.startswith("flux") else "v1"


def speak_provider(model: str) -> dict[str, str]:
    return {"type": "deepgram", "version": _provider_version(model), "model": model}


def _listen_provider(settings: Settings) -> dict[str, Any]:
    model = settings.deepgram_listen_model
    provider: dict[str, Any] = {
        "type": "deepgram",
        "version": _provider_version(model),
        "model": model,
    }
    if model == "flux-general-multi" and settings.language_hints:
        # Hints bias recognition toward the languages callers use; others are still detected.
        provider["language_hints"] = settings.language_hints
    return provider


def voice_for(settings: Settings, language: str) -> str:
    return (
        settings.deepgram_speak_model_hindi if language == "hi" else settings.deepgram_speak_model
    )


def build_agent_settings(settings: Settings, *, prompt: str, greeting: str) -> dict[str, Any]:
    """The `Settings` message that configures a Deepgram Voice Agent session for phone audio."""
    phone_audio = {"encoding": "mulaw", "sample_rate": 8000}
    return {
        "type": "Settings",
        "audio": {
            "input": phone_audio,
            "output": {**phone_audio, "container": "none"},
        },
        "agent": {
            "listen": {"provider": _listen_provider(settings)},
            "think": {
                # Deepgram-managed LLM: no separate LLM API key is needed. Temperature is left
                # unset because current Anthropic models reject sampling parameters.
                "provider": {
                    "type": settings.agent_llm_provider,
                    "model": settings.agent_llm_model,
                },
                "prompt": prompt,
                "functions": FUNCTION_DEFINITIONS,
            },
            "speak": {"provider": speak_provider(voice_for(settings, "en"))},
            "greeting": greeting,
        },
    }


def connect_to_agent(api_key: str) -> connect:
    """Open the Deepgram Voice Agent WebSocket. Tests replace this with a fake agent."""
    return connect(
        DEEPGRAM_AGENT_URL,
        additional_headers={"Authorization": f"Token {api_key}"},
        open_timeout=10,
    )


class MediaStreamBridge:
    """Relays one phone call between Twilio and Deepgram until either side hangs up."""

    def __init__(
        self,
        twilio_ws: WebSocket,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        feed: LiveFeed,
    ) -> None:
        self._twilio = twilio_ws
        self._settings = settings
        self._session_factory = session_factory
        self._feed = feed
        self._stream_sid = ""
        self._call_sid = ""
        self._call_id = ""
        self._caller_number: str | None = None
        self._language = "en"
        self._background_tasks: set[asyncio.Task[None]] = set()
        # Set while the closing goodbye is being said and played.
        self._saying_goodbye = False
        self._goodbye_audio_sent = False
        self._goodbye_played = asyncio.Event()
        self._hangup_requested = asyncio.Event()

    async def run(self) -> None:
        start = await self._receive_start()
        if start is None:
            return

        call_sid = str(start.get("callSid") or "")
        stream_sid = str(start.get("streamSid") or "")
        parameters = start.get("customParameters")
        token = str(parameters.get("token") or "") if isinstance(parameters, dict) else ""
        secret = self._settings.twilio_auth_token.get_secret_value()
        if not (call_sid and stream_sid and verify_stream_token(call_sid, token, secret)):
            logger.warning("Rejected media stream with an invalid token for call %s", call_sid)
            await self._twilio.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        self._stream_sid = stream_sid
        self._call_sid = call_sid
        async with self._session_factory() as db:
            call = await get_or_create_phone_call(
                db, call_sid=call_sid, caller_number=None, record_calls=self._settings.record_calls
            )
            self._call_id = call.id
            self._caller_number = call.caller_number

        if self._settings.record_calls:
            self._spawn(self._start_recording(call_sid))

        agent_started: float | None = None
        try:
            async with self._session_factory() as db:
                hospital = await load_hospital(db)
            agent_settings = build_agent_settings(
                self._settings,
                prompt=build_receptionist_prompt(self._settings, hospital, datetime.now(UTC)),
                greeting=greeting_for(self._settings, hospital),
            )
            hospital_tz = ZoneInfo(self._settings.hospital_timezone)
            async with connect_to_agent(
                self._settings.deepgram_api_key.get_secret_value()
            ) as agent:
                tools = ToolContext(
                    session_factory=self._session_factory,
                    settings=self._settings,
                    hospital=hospital,
                    call_id=self._call_id,
                    caller_number=self._caller_number,
                    now=lambda: wall_clock(hospital_tz),
                    feed=self._feed,
                    set_language=lambda language: self._switch_language(agent, language),
                    end_call=self._request_hangup,
                )
                agent_started = session_clock()  # Deepgram bills connected time
                await agent.send(json.dumps(agent_settings))
                await self._event(
                    CallEventType.CALL_STARTED,
                    f"Receptionist answered using {self._settings.agent_llm_model}",
                )
                await self._relay(agent, tools)
        except HospitalDataError as exc:
            logger.exception("Cannot build the receptionist prompt for call %s", call_sid)
            await self._event(CallEventType.AGENT_ERROR, f"Hospital data problem: {exc}")
        except (OSError, WebSocketException) as exc:
            logger.exception("Voice agent session failed for call %s", call_sid)
            await self._event(CallEventType.AGENT_ERROR, f"Voice agent connection failed: {exc}")
        finally:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            await self._finish(agent_started)
            if self._twilio.client_state == WebSocketState.CONNECTED:
                # Hands control back to Twilio, which plays the fallback <Say> from our TwiML.
                await self._twilio.close()

    async def _receive_start(self) -> dict[str, Any] | None:
        """Wait for Twilio's `start` event, which carries the call and stream identifiers.

        The socket is open before it's authenticated, so give up on clients that never start.
        """
        try:
            async with asyncio.timeout(STREAM_START_TIMEOUT_SECONDS):
                while True:
                    message = await self._twilio.receive_json()
                    if message.get("event") == "start":
                        start = message.get("start")
                        return start if isinstance(start, dict) else {}
        except TimeoutError:
            logger.warning("Closed a media stream that never sent its start event")
            await self._twilio.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        except WebSocketDisconnect:
            return None

    async def _relay(self, agent: ClientConnection, tools: ToolContext) -> None:
        tasks = {
            asyncio.create_task(self._forward_caller_audio(agent)),
            asyncio.create_task(self._forward_agent_events(agent, tools)),
            asyncio.create_task(self._end_call_when_due(agent)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()  # re-raise unexpected errors from either direction

    async def _forward_caller_audio(self, agent: ClientConnection) -> None:
        buffer = bytearray()
        try:
            while True:
                message = await self._twilio.receive_json()
                event = message.get("event")
                if event == "media":
                    buffer.extend(base64.b64decode(message["media"]["payload"]))
                    if len(buffer) >= _AGENT_INPUT_CHUNK_BYTES:
                        await agent.send(bytes(buffer))
                        buffer.clear()
                elif event == "mark" and message.get("mark", {}).get("name") == _GOODBYE_MARK:
                    self._goodbye_played.set()
                elif event == "stop":
                    return
        except WebSocketDisconnect:
            return

    async def _forward_agent_events(self, agent: ClientConnection, tools: ToolContext) -> None:
        try:
            async for message in agent:
                if isinstance(message, bytes):
                    await self._send_to_twilio(
                        {"event": "media", "media": {"payload": base64.b64encode(message).decode()}}
                    )
                    if self._saying_goodbye:
                        self._goodbye_audio_sent = True
                    continue

                event = json.loads(message)
                event_type = event.get("type")
                if event_type in _ACTIVITY:
                    self._feed.publish(
                        self._call_id, {"kind": "activity", "activity": _ACTIVITY[event_type]}
                    )
                match event_type:
                    case "ConversationText":
                        await self._save_turn(event.get("role", ""), event.get("content", ""))
                    case "UserStartedSpeaking" if not self._saying_goodbye:
                        # Barge-in: drop agent audio Twilio has buffered but not yet played.
                        await self._send_to_twilio({"event": "clear"})
                    case "AgentAudioDone" if self._goodbye_audio_sent:
                        # All goodbye audio is with Twilio; ask it to tell us when it has played.
                        await self._send_to_twilio(
                            {"event": "mark", "mark": {"name": _GOODBYE_MARK}}
                        )
                    case "FunctionCallRequest":
                        await self._run_functions(agent, tools, event.get("functions", []))
                    case "FunctionCallCancelled":
                        # The caller kept talking; Deepgram voids the call and expects no reply.
                        logger.info("Deepgram cancelled a function call on call %s", self._call_id)
                    case "Error":
                        logger.error(
                            "Deepgram agent error on call %s: %s",
                            self._call_id,
                            event.get("description"),
                        )
                        await self._event(
                            CallEventType.AGENT_ERROR,
                            f"Deepgram reported an error: {event.get('description')}",
                        )
                    case "Warning":
                        logger.warning(
                            "Deepgram agent warning on call %s: %s",
                            self._call_id,
                            event.get("description"),
                        )
        except WebSocketDisconnect:
            return

    async def _run_functions(
        self, agent: ClientConnection, tools: ToolContext, functions: list[dict[str, Any]]
    ) -> None:
        for function in functions:
            if not function.get("client_side"):
                continue  # Deepgram runs its own server-side functions
            name = function.get("name", "")
            result = await run_tool(name, function.get("arguments", "{}"), tools)
            response: dict[str, Any] = {
                "type": "FunctionCallResponse",
                "id": function.get("id"),
                "name": name,
                "content": json.dumps(result),
            }
            if "thought_signature" in function:  # some Gemini models require it echoed back
                response["thought_signature"] = function["thought_signature"]
            await agent.send(json.dumps(response))
            if self._saying_goodbye:
                # The goodbye is what the agent says after this result, not anything before it.
                self._goodbye_audio_sent = False

    async def _request_hangup(self, reason: str) -> None:
        """Called by a tool: hang up once the receptionist's next reply (its goodbye) has played."""
        await self._event(CallEventType.AGENT_ENDED_CALL, f"Ending the call: {reason}")
        self._saying_goodbye = True
        self._hangup_requested.set()

    async def _end_call_when_due(self, agent: ClientConnection) -> None:
        """Hang up when a tool asks to, or say goodbye and hang up at MAX_CALL_MINUTES."""
        minutes = self._settings.max_call_minutes
        try:
            await asyncio.wait_for(self._hangup_requested.wait(), timeout=minutes * 60)
        except TimeoutError:
            await self._event(
                CallEventType.TIME_LIMIT_REACHED, f"Ended the call at the {minutes:g}-minute limit"
            )
            self._saying_goodbye = True
            goodbye = _TIME_LIMIT_GOODBYES[self._language]
            # "interrupt" is never refused, even while the caller or the agent is mid-sentence.
            await agent.send(
                json.dumps(
                    {"type": "InjectAgentMessage", "behavior": "interrupt", "message": goodbye}
                )
            )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                self._goodbye_played.wait(), timeout=_GOODBYE_PLAYBACK_TIMEOUT_SECONDS
            )
        try:
            await end_call(self._settings, self._call_sid)
        except (TwilioException, OSError):
            # Closing the stream still ends the agent session; Twilio then plays the fallback.
            logger.exception("Could not hang up call %s", self._call_sid)

    async def _switch_language(self, agent: ClientConnection, language: str) -> None:
        """Swap the agent's voice. Sent before the function result, so Deepgram (which handles
        messages in order) speaks the reply that follows in the new voice."""
        if language == self._language:
            return
        update = {
            "type": "UpdateSpeak",
            "speak": {"provider": speak_provider(voice_for(self._settings, language))},
        }
        await agent.send(json.dumps(update))
        self._language = language
        async with self._session_factory() as db:
            call = await db.get(Call, self._call_id)
            if call is not None:
                call.language = language
                await db.commit()

    async def _event(self, event_type: CallEventType, message: str) -> None:
        async with self._session_factory() as db:
            await record_event(db, self._call_id, event_type, message, feed=self._feed)

    async def _finish(self, agent_started: float | None) -> None:
        """Close the call record, price the agent session, and tell live viewers it ended."""
        async with self._session_factory() as db:
            await mark_call_completed(db, self._call_id)
            summary = "Call ended"
            if agent_started is not None:
                seconds = session_clock() - agent_started
                usd_per_minute = self._settings.voice_agent_usd_per_minute
                await record_voice_agent_usage(db, self._call_id, seconds, usd_per_minute)
                cost = estimate_cost_usd(seconds, usd_per_minute)
                summary = f"Call ended after {seconds:.0f}s of agent time, about ${cost:.4f}"
            await record_event(
                db, self._call_id, CallEventType.CALL_ENDED, summary, feed=self._feed
            )
        self._feed.publish(self._call_id, {"kind": "ended"})

    async def _send_to_twilio(self, message: dict[str, Any]) -> None:
        await self._twilio.send_json({**message, "streamSid": self._stream_sid})

    async def _save_turn(self, agent_role: str, content: str) -> None:
        role = _ROLES.get(agent_role)
        text = content.strip()
        if role is None or not text:
            return
        async with self._session_factory() as db:
            db.add(TranscriptTurn(call_id=self._call_id, role=role, text=text))
            await db.commit()
        self._feed.publish(self._call_id, {"kind": "turn", "role": role.value, "text": text})

    async def _start_recording(self, call_sid: str) -> None:
        try:
            await start_call_recording(self._settings, call_sid)
        except (TwilioException, OSError):
            logger.exception("Could not start recording for call %s", call_sid)
            async with self._session_factory() as db:
                await mark_diarization_failed(db, self._call_id, "Could not start the recording.")
            await self._event(CallEventType.RECORDING_FAILED, "Twilio couldn't start the recording")
            return
        await self._event(CallEventType.RECORDING_STARTED, "Recording started")

    def _spawn(self, coro: Any) -> None:
        # Keep a reference so the task is not garbage-collected before it finishes.
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

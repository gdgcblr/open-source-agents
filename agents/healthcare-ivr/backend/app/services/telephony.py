"""Twilio helpers: TwiML to answer calls, starting call recordings and downloading them."""

import asyncio
from urllib.parse import urlsplit

import httpx
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import Settings

FALLBACK_MESSAGE = "Sorry, our assistant is unavailable right now. Please try again later. Goodbye."
RECORDING_STATUS_PATH = "/api/twilio/recording-status"
# When a caller withholds their number, Twilio's `From` is "anonymous" or one of these digit
# spellings of ANONYMOUS, RESTRICTED, UNAVAILABLE, BLOCKED and UNKNOWN. Every withheld caller
# would share them, so they must never identify a patient.
# https://help.twilio.com/articles/223179988-Why-am-I-getting-calls-from-these-strange-numbers-
_WITHHELD_CALLER_IDS = frozenset(
    {"+266696687", "+7378742833", "+86282452253", "+2562533", "+8656696"}
)


def caller_number_or_none(value: str | None) -> str | None:
    """The caller's number, or None when Twilio reports a withheld or unknown caller ID."""
    value = (value or "").strip()
    if not any(char.isdigit() for char in value) or value in _WITHHELD_CALLER_IDS:
        return None
    return value


def is_twilio_url(url: str) -> bool:
    """Recordings are only downloaded from Twilio, because the request carries our credentials."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and (host == "twilio.com" or host.endswith(".twilio.com"))


def build_answer_twiml(stream_url: str, token: str) -> str:
    """Connect the call to our Media Stream WebSocket, passing a per-call auth token."""
    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=stream_url)
    stream.parameter(name="token", value=token)
    response.append(connect)
    # Twilio only reaches this verb if the stream ends while the caller is still on the line,
    # for example when the voice agent cannot be reached.
    response.say(FALLBACK_MESSAGE)
    return str(response)


async def start_call_recording(settings: Settings, call_sid: str) -> str:
    """Start recording an in-progress call. Twilio reports completion to the status callback."""
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token.get_secret_value())
    recording = await asyncio.to_thread(
        client.calls(call_sid).recordings.create,
        recording_status_callback=settings.public_url(RECORDING_STATUS_PATH),
        recording_status_callback_event=["completed absent"],
        # Both parties mixed into one channel: Deepgram diarization separates the speakers.
        recording_channels="mono",
    )
    return recording.sid


async def end_call(settings: Settings, call_sid: str) -> None:
    """Hang up an in-progress call. Unlike closing the media stream, this skips the fallback
    <Say>, so the caller hears the receptionist's goodbye and nothing after it."""
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token.get_secret_value())
    await asyncio.to_thread(client.calls(call_sid).update, status="completed")


async def download_recording(settings: Settings, recording_url: str) -> bytes:
    """Download a completed recording as MP3. Twilio media URLs require HTTP Basic auth."""
    auth = (settings.twilio_account_sid, settings.twilio_auth_token.get_secret_value())
    async with httpx.AsyncClient(
        auth=auth, follow_redirects=True, timeout=httpx.Timeout(60.0, connect=10.0)
    ) as client:
        response = await client.get(f"{recording_url}.mp3")
        response.raise_for_status()
        return response.content

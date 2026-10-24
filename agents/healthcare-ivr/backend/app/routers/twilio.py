"""Twilio integration: answer incoming calls, stream call audio and receive recordings."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Response, WebSocket, status
from sqlalchemy import select

from app.dependencies import DbSession, FeedDep, SessionFactoryDep, SettingsDep, StorageDep
from app.models import Call, DiarizationStatus
from app.security import create_stream_token, verify_twilio_signature
from app.services.calls import get_or_create_phone_call
from app.services.diarization import fetch_recording_and_diarize
from app.services.telephony import build_answer_twiml, caller_number_or_none, is_twilio_url
from app.services.voice_agent import MediaStreamBridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/twilio", tags=["twilio"])

MEDIA_STREAM_PATH = "/api/twilio/media-stream"


@router.post("/voice", dependencies=[Depends(verify_twilio_signature)])
async def answer_call(
    db: DbSession,
    settings: SettingsDep,
    call_sid: Annotated[str, Form(alias="CallSid")],
    caller_number: Annotated[str | None, Form(alias="From")] = None,
    called_number: Annotated[str | None, Form(alias="To")] = None,
) -> Response:
    """Webhook for incoming calls: connect the caller to the voice agent over a Media Stream.

    Point every hospital number you want answered at this URL; `To` records which one rang.
    """
    await get_or_create_phone_call(
        db,
        call_sid=call_sid,
        # A withheld number is stored as unknown, so the receptionist asks for one instead.
        caller_number=caller_number_or_none(caller_number),
        called_number=called_number,
        record_calls=settings.record_calls,
    )
    twiml = build_answer_twiml(
        stream_url=settings.public_ws_url(MEDIA_STREAM_PATH),
        token=create_stream_token(call_sid, settings.twilio_auth_token.get_secret_value()),
    )
    return Response(content=twiml, media_type="application/xml")


@router.post(
    "/recording-status",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_twilio_signature)],
)
async def recording_status(
    background_tasks: BackgroundTasks,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
    call_sid: Annotated[str, Form(alias="CallSid")],
    recording_status: Annotated[str, Form(alias="RecordingStatus")],
    recording_url: Annotated[str | None, Form(alias="RecordingUrl")] = None,
) -> None:
    """Recording callback: download the finished recording and diarize it in the background."""
    call = await db.scalar(select(Call).where(Call.twilio_call_sid == call_sid))
    if call is None:
        logger.warning("Recording callback for unknown call %s", call_sid)
        return

    if recording_status != "completed" or not recording_url:
        call.diarization_status = DiarizationStatus.FAILED
        call.diarization_error = f"Twilio reported recording status '{recording_status}'."
        await db.commit()
        return
    if not is_twilio_url(recording_url):
        logger.warning("Ignored a recording URL outside Twilio for call %s", call_sid)
        call.diarization_status = DiarizationStatus.FAILED
        call.diarization_error = (
            "The recording URL wasn't on Twilio's domain, so it wasn't fetched."
        )
        await db.commit()
        return

    background_tasks.add_task(
        fetch_recording_and_diarize,
        call.id,
        recording_url,
        session_factory=session_factory,
        storage=storage,
        settings=settings,
    )


@router.websocket("/media-stream")
async def media_stream(
    websocket: WebSocket,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    feed: FeedDep,
) -> None:
    """Bidirectional Twilio Media Stream, bridged to a Deepgram Voice Agent session."""
    await websocket.accept()
    if not settings.twilio_configured:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return
    bridge = MediaStreamBridge(
        websocket, settings=settings, session_factory=session_factory, feed=feed
    )
    await bridge.run()

"""Dashboard API: browse calls, follow live calls, upload recordings, play and delete audio."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, FeedDep, SessionFactoryDep, SettingsDep, StorageDep
from app.models import (
    Call,
    CallEventType,
    CallSource,
    CallStatus,
    DiarizationStatus,
    TranscriptTurn,
)
from app.schemas import (
    CallDetail,
    CallPage,
    CallSummary,
    LiveCall,
    LiveCallList,
    TranscriptTurnOut,
)
from app.security import require_dashboard_user
from app.services.diarization import diarize_call
from app.services.events import record_event
from app.services.storage import ALLOWED_AUDIO_SUFFIXES, UploadTooLargeError

router = APIRouter(
    prefix="/api/calls",
    tags=["calls"],
    dependencies=[Depends(require_dashboard_user)],
)

# Comment lines keep idle server-sent-event connections open through proxies.
_KEEP_ALIVE_SECONDS = 15


def _sse(message: dict[str, Any]) -> str:
    return f"data: {json.dumps(message)}\n\n"


async def _get_call_or_404(
    db: AsyncSession, call_id: str, *, with_transcripts: bool = False
) -> Call:
    options = (
        [
            selectinload(Call.turns),
            selectinload(Call.utterances),
            selectinload(Call.appointments),
            selectinload(Call.events),
        ]
        if with_transcripts
        else []
    )
    call = await db.get(Call, call_id, options=options)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")
    return call


@router.get("")
async def list_calls(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CallPage:
    total = await db.scalar(select(func.count()).select_from(Call)) or 0
    total_cost = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.coalesce(Call.agent_cost_usd, 0)
                    + func.coalesce(Call.transcription_cost_usd, 0)
                ),
                0,
            )
        )
    )
    rows = await db.scalars(
        select(Call)
        .order_by(Call.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return CallPage(
        items=[CallSummary.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_cost_usd=round(total_cost or 0, 4),
    )


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_recording(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
) -> CallSummary:
    """Store an audio file and diarize it in the background."""
    filename = Path(file.filename or "recording").name
    suffix = Path(filename).suffix.lower()
    content_type = file.content_type or ""
    if suffix not in ALLOWED_AUDIO_SUFFIXES or not content_type.startswith(("audio/", "video/")):
        allowed = ", ".join(sorted(ALLOWED_AUDIO_SUFFIXES))
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Upload an audio file ({allowed})."
        )

    call = Call(
        id=str(uuid.uuid4()),
        source=CallSource.UPLOAD,
        status=CallStatus.COMPLETED,
        title=filename[:255],
        audio_content_type=content_type,
        diarization_status=DiarizationStatus.PENDING,
    )
    try:
        call.audio_filename = await storage.save_stream(
            call.id, suffix, file.file, settings.max_upload_mb * 1024 * 1024
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc

    db.add(call)
    await db.commit()
    await record_event(db, call.id, CallEventType.RECORDING_RECEIVED, f"Uploaded {filename}")
    background_tasks.add_task(
        diarize_call, call.id, session_factory=session_factory, storage=storage, settings=settings
    )
    return CallSummary.model_validate(call)


@router.get("/live")
async def list_live_calls(db: DbSession) -> LiveCallList:
    """Phone calls happening now, each with the latest thing said."""
    calls = await db.scalars(
        select(Call)
        .where(Call.status == CallStatus.IN_PROGRESS, Call.source == CallSource.PHONE)
        .order_by(Call.started_at.desc())
    )
    items: list[LiveCall] = []
    for call in calls:
        latest = await db.scalar(
            select(TranscriptTurn)
            .where(TranscriptTurn.call_id == call.id)
            .order_by(TranscriptTurn.id.desc())
            .limit(1)
        )
        summary = {field: getattr(call, field) for field in CallSummary.model_fields}
        latest_turn = TranscriptTurnOut.model_validate(latest) if latest else None
        items.append(LiveCall.model_validate({**summary, "latest_turn": latest_turn}))
    return LiveCallList(items=items)


@router.get("/{call_id}/stream")
async def stream_call(
    call_id: str, request: Request, db: DbSession, feed: FeedDep
) -> StreamingResponse:
    """Server-sent events while a call is live: new turns, timeline events, who is talking.

    Each message is a hint to refetch the call; `activity` messages carry the speaking state.
    The stream ends with an `ended` message, immediately if the call is already over.
    """
    call = await _get_call_or_404(db, call_id)
    is_live = call.status == CallStatus.IN_PROGRESS

    async def updates() -> AsyncIterator[str]:
        if not is_live:
            yield _sse({"kind": "ended"})
            return
        async with feed.subscribe(call_id) as queue:
            yield _sse({"kind": "subscribed"})
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=_KEEP_ALIVE_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(message)
                if message["kind"] == "ended":
                    return

    return StreamingResponse(
        updates(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{call_id}")
async def get_call(call_id: str, db: DbSession) -> CallDetail:
    call = await _get_call_or_404(db, call_id, with_transcripts=True)
    return CallDetail.model_validate(call)


@router.get("/{call_id}/audio")
async def get_call_audio(call_id: str, db: DbSession, storage: StorageDep) -> FileResponse:
    call = await _get_call_or_404(db, call_id)
    path = storage.path_for(call.audio_filename) if call.audio_filename else None
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No audio stored for this call")
    return FileResponse(path, media_type=call.audio_content_type or "application/octet-stream")


@router.delete("/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_call(call_id: str, db: DbSession, storage: StorageDep) -> None:
    """Delete a call, its transcripts and its stored audio."""
    call = await _get_call_or_404(db, call_id, with_transcripts=True)
    if call.audio_filename:
        storage.delete(call.audio_filename)
    await db.delete(call)
    await db.commit()

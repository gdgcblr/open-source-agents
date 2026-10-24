"""Persistence helpers for phone call records shared by the webhook and the media stream."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Call, CallSource, CallStatus, DiarizationStatus
from app.services.costs import estimate_cost_usd


async def get_or_create_phone_call(
    db: AsyncSession,
    *,
    call_sid: str,
    caller_number: str | None,
    record_calls: bool,
    called_number: str | None = None,
) -> Call:
    """Return the call for `call_sid`, creating it on first sight (Twilio may retry webhooks)."""
    call = await db.scalar(select(Call).where(Call.twilio_call_sid == call_sid))
    if call is None:
        call = Call(
            source=CallSource.PHONE,
            status=CallStatus.IN_PROGRESS,
            twilio_call_sid=call_sid,
            caller_number=caller_number,
            called_number=called_number,
            language="en",  # every call opens in English; the caller can switch to Hindi
            diarization_status=(
                DiarizationStatus.PENDING if record_calls else DiarizationStatus.SKIPPED
            ),
        )
        db.add(call)
        await db.commit()
    return call


async def mark_call_completed(db: AsyncSession, call_id: str) -> None:
    call = await db.get(Call, call_id)
    if call is None or call.status == CallStatus.COMPLETED:
        return
    ended_at = datetime.now(UTC)
    call.status = CallStatus.COMPLETED
    call.ended_at = ended_at
    call.duration_seconds = (ended_at - call.started_at).total_seconds()
    await db.commit()


async def close_orphaned_calls(db: AsyncSession) -> int:
    """Mark calls left "in progress" by a previous run as completed; none can still be live."""
    result = await db.execute(
        update(Call)
        .where(Call.status == CallStatus.IN_PROGRESS)
        .values(status=CallStatus.COMPLETED, ended_at=datetime.now(UTC))
    )
    await db.commit()
    return result.rowcount or 0


async def record_voice_agent_usage(
    db: AsyncSession, call_id: str, seconds: float, usd_per_minute: float
) -> None:
    """Store how long the Deepgram agent session ran and what it is estimated to cost."""
    call = await db.get(Call, call_id)
    if call is None:
        return
    call.agent_seconds = round(seconds, 1)
    call.agent_cost_usd = estimate_cost_usd(seconds, usd_per_minute)
    await db.commit()


async def mark_diarization_failed(db: AsyncSession, call_id: str, message: str) -> None:
    call = await db.get(Call, call_id)
    if call is None:
        return
    call.diarization_status = DiarizationStatus.FAILED
    call.diarization_error = message
    await db.commit()

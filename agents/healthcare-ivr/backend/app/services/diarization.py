"""Background jobs that turn call audio into speaker-diarized transcripts."""

import logging

import httpx
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db import SessionFactory
from app.models import Call, CallEventType, DiarizationStatus, Utterance
from app.services.calls import mark_diarization_failed
from app.services.costs import estimate_cost_usd
from app.services.deepgram import DeepgramDiarizer, DeepgramError
from app.services.events import record_event
from app.services.storage import RecordingStorage
from app.services.telephony import download_recording

logger = logging.getLogger(__name__)


async def diarize_call(
    call_id: str,
    *,
    session_factory: SessionFactory,
    storage: RecordingStorage,
    settings: Settings,
) -> None:
    """Send the call's stored audio to Deepgram and replace its utterances with the result."""
    async with session_factory() as db:
        call = await db.get(Call, call_id, options=[selectinload(Call.utterances)])
        if call is None or call.audio_filename is None:
            logger.warning("Skipping diarization for call %s: no audio stored", call_id)
            return

        call.diarization_status = DiarizationStatus.PROCESSING
        call.diarization_error = None
        await db.commit()

        diarizer = DeepgramDiarizer(
            settings.deepgram_api_key.get_secret_value(),
            settings.deepgram_diarize_model,
            language=settings.deepgram_diarize_language,
            language_hints=settings.language_hints,
        )
        try:
            audio = await storage.read(call.audio_filename)
            result = await diarizer.diarize(
                audio, call.audio_content_type or "application/octet-stream"
            )
        except DeepgramError as exc:
            logger.warning("Diarization failed for call %s: %s", call_id, exc)
            await mark_diarization_failed(db, call_id, str(exc))
            await record_event(
                db, call_id, CallEventType.TRANSCRIPTION_FAILED, f"Transcription failed: {exc}"
            )
            return
        except Exception:
            # Job boundary: record the failure so the call never stays "processing" forever.
            logger.exception("Unexpected error while diarizing call %s", call_id)
            message = "Unexpected error while diarizing; see server logs."
            await mark_diarization_failed(db, call_id, message)
            await record_event(db, call_id, CallEventType.TRANSCRIPTION_FAILED, message)
            return

        call.utterances = [
            Utterance(
                speaker=item.speaker,
                start=item.start,
                end=item.end,
                text=item.text,
                confidence=item.confidence,
            )
            for item in result.utterances
        ]
        call.speaker_count = result.speaker_count
        if call.duration_seconds is None:
            call.duration_seconds = result.duration_seconds
        if result.duration_seconds is not None:
            call.transcription_cost_usd = estimate_cost_usd(
                result.duration_seconds, settings.transcription_usd_per_minute
            )
        call.diarization_status = DiarizationStatus.COMPLETED
        await db.commit()
        cost = f", about ${call.transcription_cost_usd:.4f}" if call.transcription_cost_usd else ""
        await record_event(
            db,
            call_id,
            CallEventType.TRANSCRIPTION_COMPLETED,
            f"Transcribed {len(result.utterances)} segments from "
            f"{result.speaker_count} speakers{cost}",
        )
        logger.info(
            "Diarized call %s: %d utterances, %d speakers",
            call_id,
            len(result.utterances),
            result.speaker_count,
        )


async def fetch_recording_and_diarize(
    call_id: str,
    recording_url: str,
    *,
    session_factory: SessionFactory,
    storage: RecordingStorage,
    settings: Settings,
) -> None:
    """Download a finished Twilio recording, store it, then diarize it."""
    try:
        audio = await download_recording(settings, recording_url)
        filename = await storage.save_bytes(call_id, ".mp3", audio)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Could not download recording for call %s: %s", call_id, exc)
        async with session_factory() as db:
            message = f"Could not download the recording: {exc}"
            await mark_diarization_failed(db, call_id, message)
            await record_event(db, call_id, CallEventType.TRANSCRIPTION_FAILED, message)
        return

    async with session_factory() as db:
        call = await db.get(Call, call_id)
        if call is None:
            storage.delete(filename)
            return
        call.audio_filename = filename
        call.audio_content_type = "audio/mpeg"
        await db.commit()
        await record_event(
            db, call_id, CallEventType.RECORDING_RECEIVED, "Recording received from Twilio"
        )

    await diarize_call(call_id, session_factory=session_factory, storage=storage, settings=settings)

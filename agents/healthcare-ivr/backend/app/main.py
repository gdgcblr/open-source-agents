"""FastAPI application factory. Run with `uvicorn app.main:create_app --factory`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory, init_db
from app.routers import analytics, appointments, calls, health, hospital, twilio
from app.services.calls import close_orphaned_calls
from app.services.events import LiveFeed
from app.services.hospital import build_receptionist_prompt
from app.services.hospital_store import load_hospital, seed_hospital
from app.services.storage import RecordingStorage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    await init_db(engine)
    session_factory = create_session_factory(engine)

    async with session_factory() as db:
        if await seed_hospital(db, settings):
            logger.info("Loaded the hospital from %s", settings.hospital_dir)
        if orphaned := await close_orphaned_calls(db):
            logger.warning("Closed %d calls left in progress by the previous run", orphaned)
        # Fail at startup, not mid-call, if the hospital data can't make a valid prompt.
        build_receptionist_prompt(settings, await load_hospital(db), datetime.now(UTC))

    storage = RecordingStorage(settings.recordings_dir)
    storage.ensure_root()

    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.call_feed = LiveFeed()
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title="Hospital Reception IVR",
        description="AI receptionist for hospital phone lines, with diarized call recordings.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.include_router(health.router)
    app.include_router(calls.router)
    app.include_router(hospital.router)
    app.include_router(appointments.router)
    app.include_router(analytics.router)
    app.include_router(twilio.router)
    return app

"""FastAPI dependencies. Shared resources live on `app.state` and are created in the lifespan."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.config import Settings
from app.db import SessionFactory
from app.services.events import LiveFeed
from app.services.storage import RecordingStorage


def get_app_settings(conn: HTTPConnection) -> Settings:
    return conn.app.state.settings


def get_session_factory(conn: HTTPConnection) -> SessionFactory:
    return conn.app.state.session_factory


def get_storage(conn: HTTPConnection) -> RecordingStorage:
    return conn.app.state.storage


def get_feed(conn: HTTPConnection) -> LiveFeed:
    return conn.app.state.call_feed


async def get_db(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
StorageDep = Annotated[RecordingStorage, Depends(get_storage)]
FeedDep = Annotated[LiveFeed, Depends(get_feed)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

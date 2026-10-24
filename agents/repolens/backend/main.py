"""
RepoLens — FastAPI Application

Entry point for the backend REST API.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("RepoLens backend starting — model: %s", settings.gemini_model)
    logger.info("Gemini configured: %s", settings.gemini_available)
    # Attempt schema init (non-fatal if DB is unavailable)
    try:
        from backend.db import init_schema
        schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
        init_schema(schema_path)
    except Exception as exc:
        logger.warning("Database schema init skipped: %s", exc)
    yield
    logger.info("RepoLens backend shutting down.")


app = FastAPI(
    title="RepoLens API",
    description="AI-powered GitHub repository security auditor.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the React dev server (port 5173) and production builds
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:80",
        "http://localhost",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router, prefix="/api")

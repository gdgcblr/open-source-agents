"""FastAPI application for SQLBuddy's local web interface."""

import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import HistoryStore
from .models import Answer, QueryRequest, QueryResponse, RenameSessionRequest, SchemaInput, SessionDetail, SessionSummary
from .rate_limit import RateLimiter
from .service import ServiceError, generate_answer

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = HistoryStore(settings.database_path)
    store.initialize()
    app.state.history = store
    app.state.answer_generator = generate_answer
    yield


app = FastAPI(
    title="SQLBuddy API",
    description="Local API for read-only SQL suggestions and saved query history.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_middleware(RateLimiter, settings.rate_limit_requests, settings.rate_limit_window_seconds)


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(part) for part in error["loc"] if part != "body"),
         "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": "Please check the request fields and try again.", "details": details}},
    )


@app.exception_handler(sqlite3.Error)
async def database_error_handler(_request: Request, _exc: sqlite3.Error):
    logger.exception("SQLBuddy history database operation failed")
    return JSONResponse(status_code=503, content={"error": {"code": "history_unavailable", "message": "Saved history is temporarily unavailable."}})


@app.get("/api/v1/health")
def health(request: Request):
    """Report service and history availability without exposing secrets."""
    available = request.app.state.history.check()
    return JSONResponse(status_code=200 if available else 503, content={"status": "ok" if available else "degraded", "history": "available" if available else "unavailable"})


@app.post("/api/v1/queries", response_model=QueryResponse, status_code=201)
def create_query(payload: QueryRequest, request: Request):
    """Generate one answer and persist it in the selected history session."""
    if len(payload.question) > settings.max_question_chars:
        return JSONResponse(status_code=413, content={"error": {"code": "question_too_large", "message": "The question is too long."}})
    schema_text = payload.schema_context.model_dump_json() if payload.schema_context else ""
    if len(schema_text) > settings.max_schema_chars:
        return JSONResponse(status_code=413, content={"error": {"code": "schema_too_large", "message": "The schema details are too large."}})
    answer: Answer = request.app.state.answer_generator(payload)
    try:
        session_id, created_at = request.app.state.history.add_message(payload.session_id, payload.question, answer.model_dump(), payload.dialect)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return QueryResponse(session_id=session_id, answer=answer, dialect=payload.dialect, created_at=datetime.fromisoformat(created_at))


@app.get("/api/v1/sessions", response_model=list[SessionSummary])
def list_sessions(request: Request):
    return request.app.state.history.list_sessions()


@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: UUID, request: Request):
    session = request.app.state.history.get_session(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return session


@app.patch("/api/v1/sessions/{session_id}", response_model=SessionSummary)
def rename_session(session_id: UUID, payload: RenameSessionRequest, request: Request):
    if not request.app.state.history.rename_session(session_id, payload.title):
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return next(session for session in request.app.state.history.list_sessions() if session["id"] == str(session_id))


@app.delete("/api/v1/sessions/{session_id}", status_code=204)
def delete_session(session_id: UUID, request: Request):
    if not request.app.state.history.delete_session(session_id):
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return None


@app.get("/api/v1/schema/example", response_model=SchemaInput)
def schema_example():
    """Return a small example schema to help format optional context."""
    return SchemaInput.model_validate({"tables": [{"name": "users", "columns": ["id", "email", "created_at"]}]})

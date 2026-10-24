"""Web UI: live fishbone that fills in as the agents investigate.

    uvicorn server:app --port 8080
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse  # noqa: E402

from ishikawa.render import to_markdown  # noqa: E402
from ishikawa.replay import audit_path, has_recording, record, replay  # noqa: E402
from ishikawa.runner import investigate, to_sse  # noqa: E402
from ishikawa.schema import RCAReport  # noqa: E402
from ishikawa.tools import list_incidents, load_incident  # noqa: E402

WEB = Path(__file__).parent / "web"
log = logging.getLogger("ishikawa")
app = FastAPI(title="Ishikawa RCA")

# Abuse guardrails for the paid endpoint: every investigation costs ~20 model calls.
MAX_CONCURRENT = int(os.getenv("ISHIKAWA_MAX_CONCURRENT", "2"))
RATE_PER_MIN = int(os.getenv("ISHIKAWA_RATE_PER_MIN", "6"))
API_TOKEN = os.getenv("ISHIKAWA_API_TOKEN", "")  # set it whenever the server is reachable beyond localhost
_running = asyncio.Semaphore(MAX_CONCURRENT)
_recent: dict[str, deque] = defaultdict(deque)


def live_available() -> bool:
    """True when Gemini credentials are configured; otherwise the UI falls back to recorded replays."""
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in ("TRUE", "1"):
        return bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    key = os.getenv("GOOGLE_API_KEY", "")
    return bool(key) and not key.startswith("your_")


def _guard_request(request: Request) -> None:
    # Browsers send Sec-Fetch-Site; a cross-site page must not be able to spend our model budget.
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "cross-site requests are not allowed")
    if API_TOKEN and not secrets.compare_digest(request.query_params.get("token", ""), API_TOKEN):
        raise HTTPException(401, "missing or invalid token")
    client = request.client.host if request.client else "unknown"
    window, now = _recent[client], time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_PER_MIN:
        raise HTTPException(429, f"rate limit: {RATE_PER_MIN} investigations per minute")
    window.append(now)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def config() -> dict:
    return {"live": live_available(), "replay": {i["id"]: has_recording(i["id"]) for i in list_incidents()}}


@app.get("/api/incidents")
def incidents() -> list[dict]:
    return list_incidents()


@app.get("/api/incidents/{incident_id}")
def incident(incident_id: str) -> dict:
    try:  # ground truth stays server-side: the UI never sees the expected answer
        return {k: v for k, v in load_incident(incident_id).items() if k != "expected"}
    except ValueError as e:
        raise HTTPException(404, "unknown incident") from e


@app.get("/api/investigate/{incident_id}")
async def run(incident_id: str, request: Request, mode: str = "auto", speed: float = 1.0) -> StreamingResponse:
    incident(incident_id)  # 404 early on unknown ids
    use_replay = mode == "replay" or (mode == "auto" and not live_available())
    if use_replay and not has_recording(incident_id):
        raise HTTPException(404, "no recording for this incident; run python -m ishikawa.eval with a key")
    if not use_replay:  # replays cost nothing, so only live runs are rate limited
        _guard_request(request)
        if _running.locked():
            raise HTTPException(429, f"{MAX_CONCURRENT} investigations already running; try again shortly")

    async def stream():
        async with (asyncio.Semaphore(1) if use_replay else _running):
            try:
                speed_ok = min(max(speed, 0.5), 20.0)
                events = (replay(incident_id, speed=speed_ok) if use_replay
                          else record(investigate(incident_id), incident_id, dest=audit_path(incident_id)))
                async for ev in events:
                    yield to_sse(ev)
            except Exception:  # keep details server-side; the browser gets a reference id only
                ref = secrets.token_hex(4)
                log.exception("investigation failed ref=%s incident=%s", ref, incident_id)
                yield to_sse({"type": "error", "message": f"Investigation failed (ref {ref}). Check server logs."})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/markdown")
def markdown(payload: dict) -> PlainTextResponse:
    report = RCAReport.model_validate(payload.get("report", payload))
    return PlainTextResponse(to_markdown(report, guardrails=payload.get("guardrails"), metrics=payload.get("metrics")),
                             media_type="text/markdown")

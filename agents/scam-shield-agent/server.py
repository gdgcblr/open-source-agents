"""Scam Shield web server: serves the lightweight PWA and the /api/check endpoint."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
import httpx  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import errors, types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from scam_shield.agent import MODEL, pipeline_for_key, root_agent  # noqa: E402
from scam_shield.tools import rules_verdict  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
log = logging.getLogger("scam-shield")

STATIC = Path(__file__).parent / "static"
APP_NAME = "scam_shield"
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
MAX_IMAGE_BYTES = 1_500_000
LANGUAGES = {
    "en": "English", "hi": "Hindi", "kn": "Kannada", "ta": "Tamil",
    "te": "Telugu", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali",
}

QUOTA_COOLDOWN_SECONDS = 60


def load_api_keys() -> list[str]:
    """Reads GOOGLE_API_KEYS, then GOOGLE_API_KEY and GEMINI_API_KEY (all comma-separated, any number)."""
    raw = ",".join(os.getenv(name, "") for name in ("GOOGLE_API_KEYS", "GOOGLE_API_KEY", "GEMINI_API_KEY"))
    keys: list[str] = []
    for key in (k.strip() for k in raw.split(",")):
        if key and key not in keys:
            keys.append(key)
    return keys


class KeyPool:
    """Tracks which Gemini API keys are usable. Keys are only ever referred to by number."""

    def __init__(self, keys: list[str], clock=time.monotonic):
        self.keys = keys
        self.clock = clock
        self.disabled: set[int] = set()
        self.cooldown_until: dict[int, float] = {}
        self.start = 0  # index of the last key that worked

    def __len__(self) -> int:
        return len(self.keys)

    def status(self, i: int) -> str:
        if i in self.disabled:
            return "invalid"
        if self.cooldown_until.get(i, 0) > self.clock():
            return "quota"
        return "ok"

    def available(self) -> int:
        return sum(self.status(i) == "ok" for i in range(len(self.keys)))

    def order(self) -> list[int]:
        """All key indexes, starting from the last one that worked."""
        n = len(self.keys)
        return [(self.start + step) % n for step in range(n)]

    def disable(self, i: int) -> None:
        self.disabled.add(i)

    def cool_down(self, i: int, seconds: float) -> None:
        self.cooldown_until[i] = self.clock() + seconds

    def mark_good(self, i: int) -> None:
        self.start = i
        self.cooldown_until.pop(i, None)


class AllKeysFailed(Exception):
    def __init__(self, info: dict):
        super().__init__(info["message"])
        self.info = info


def classify_error(exc: BaseException) -> tuple[str, float | None]:
    """Sorts an AI failure into invalid / quota / unreachable (try the next key) or other (stop).

    Returns (kind, cooldown_seconds); cooldown_seconds is only set for quota errors.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
            exc = exc.exceptions[0]
            continue
        if isinstance(exc, errors.APIError):
            text = f"{exc.status} {exc.message}".lower()
            if exc.code in (401, 403) or (exc.code == 400 and any(
                    w in text for w in ("api key", "api_key", "expired", "permission"))):
                return "invalid", None
            if exc.code == 429:
                return "quota", _retry_after(exc)
            if exc.code and exc.code >= 500:
                return "unreachable", None
            return "other", None
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError,
                            asyncio.TimeoutError, ConnectionError)):
            return "unreachable", None
        exc = exc.__cause__ or exc.__context__
    return "other", None


def _retry_after(exc: errors.APIError) -> float:
    match = re.search(r"retry (?:in|after) ([\d.]+)\s*s", str(exc.message or ""), re.I)
    if not match:
        match = re.search(r"'retryDelay': '([\d.]+)s'", str(exc.details or ""))
    return float(match.group(1)) if match else QUOTA_COOLDOWN_SECONDS


def _failure_info(pool: KeyPool, last_status: dict[int, str]) -> dict:
    statuses = [last_status.get(i) or pool.status(i) for i in range(len(pool))]
    counts = {s: statuses.count(s) for s in ("invalid", "quota", "unreachable")}
    n = len(pool)
    return {
        "code": "all_keys_failed",
        "message": (f"AI unavailable: all {n} API key{'s' if n != 1 else ''} failed "
                    f"({counts['invalid']} invalid, {counts['quota']} over quota, "
                    f"{counts['unreachable']} unreachable). Update GOOGLE_API_KEYS in .env."),
        "keys": [{"n": i + 1, "status": s} for i, s in enumerate(statuses)],
    }


NO_KEYS_ERROR = {"code": "no_keys",
                 "message": "AI unavailable: no API key configured. Set GOOGLE_API_KEYS in .env."}

sessions = InMemorySessionService()
key_pool = KeyPool(load_api_keys())
_runners: dict[str, Runner] = {}


def _runner_for(key_index: int | None) -> Runner:
    """One Runner per key, built on first use. None means the default (Vertex AI) pipeline."""
    if key_index is None:
        cache_key, make_agent = "default", lambda: root_agent
    else:
        api_key = key_pool.keys[key_index]
        cache_key, make_agent = api_key, lambda: pipeline_for_key(api_key)
    if cache_key not in _runners:
        _runners[cache_key] = Runner(app_name=APP_NAME, agent=make_agent(), session_service=sessions)
    return _runners[cache_key]

app = FastAPI(title="Scam Shield", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=500)
_hits: dict[str, deque] = defaultdict(deque)


class CheckRequest(BaseModel):
    text: str = Field(default="", max_length=5000)
    image_base64: str | None = Field(default=None, max_length=2_100_000)
    image_mime: str = "image/jpeg"
    language: str = "en"
    simple: bool = False


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        return True
    window.append(now)
    return False


def _ai_enabled() -> bool:
    return bool(len(key_pool) or os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"))


async def run_agent(runner: Runner, text: str, image: bytes | None, mime: str, language: str,
                    simple: bool) -> dict:
    """Runs the multi-agent pipeline once and returns the structured verdict."""
    parts = []
    if text:
        parts.append(types.Part(text=f"Message to check:\n\"\"\"\n{text}\n\"\"\""))
    if image:
        parts.append(types.Part(text="Screenshot of the message to check:"))
        parts.append(types.Part.from_bytes(data=image, mime_type=mime))
    session_id = uuid.uuid4().hex
    await sessions.create_session(
        app_name=APP_NAME, user_id="web", session_id=session_id,
        state={"language": LANGUAGES.get(language, "English"), "simple_mode": "on" if simple else "off",
               "today": date.today().strftime("%d %B %Y")},
    )
    try:
        async for _ in runner.run_async(user_id="web", session_id=session_id,
                                        new_message=types.Content(role="user", parts=parts)):
            pass
        session = await sessions.get_session(app_name=APP_NAME, user_id="web", session_id=session_id)
        verdict = session.state.get("verdict")
        if not isinstance(verdict, dict):
            raise RuntimeError("Agent did not return a verdict")
        return verdict
    finally:
        await sessions.delete_session(app_name=APP_NAME, user_id="web", session_id=session_id)


async def run_with_failover(text: str, image: bytes | None, mime: str, language: str, simple: bool) -> dict:
    """Tries each usable key in turn, starting from the last one that worked.

    Raises AllKeysFailed when no key could run the check. Errors that are not about
    the key (they would fail on every key) are re-raised straight away.
    """
    if not len(key_pool):  # Vertex AI: no keys to rotate
        return await run_agent(_runner_for(None), text, image, mime, language, simple)
    last_status: dict[int, str] = {}
    for i in key_pool.order():
        if key_pool.status(i) != "ok":
            continue
        try:
            result = await run_agent(_runner_for(i), text, image, mime, language, simple)
        except Exception as exc:  # noqa: BLE001 - sorted by classify_error
            kind, cooldown = classify_error(exc)
            if kind == "other":
                raise
            code = getattr(exc, "code", None)
            log.warning("AI key #%d failed: %s%s", i + 1, kind, f" (HTTP {code})" if code else "")
            if kind == "invalid":
                key_pool.disable(i)
            elif kind == "quota":
                key_pool.cool_down(i, cooldown)
                log.warning("AI key #%d on cooldown for %.0f s", i + 1, cooldown)
            last_status[i] = kind
            continue
        key_pool.mark_good(i)
        return result
    raise AllKeysFailed(_failure_info(key_pool, last_status))


@app.post("/api/check")
async def check(req: CheckRequest, request: Request):
    if _rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(429, "Too many checks. Please wait a minute.")
    text = req.text.strip()
    image = None
    if req.image_base64:
        if req.image_mime not in ("image/jpeg", "image/png", "image/webp"):
            raise HTTPException(400, "Unsupported image type")
        try:
            image = base64.b64decode(req.image_base64.split(",")[-1], validate=True)
        except ValueError:
            raise HTTPException(400, "Invalid image data")
        if len(image) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image too large")
    if not text and not image:
        raise HTTPException(400, "Please provide a message or a screenshot")

    started = time.perf_counter()
    ai_error = None
    if _ai_enabled():
        try:
            result = await run_with_failover(text, image, req.image_mime, req.language, req.simple)
            result["mode"] = "ai"
            result["model"] = MODEL
            result["seconds"] = round(time.perf_counter() - started, 2)
            return result
        except AllKeysFailed as exc:
            ai_error = exc.info
            log.warning("%s Falling back to rules.", ai_error["message"])
        except Exception:  # noqa: BLE001 - any other AI failure falls back to rules
            log.exception("AI check failed; falling back to rules")
    else:
        ai_error = NO_KEYS_ERROR
    if not text:
        if ai_error and ai_error["code"] == "all_keys_failed":
            raise HTTPException(503, ai_error["message"])
        raise HTTPException(503, "AI is unavailable, and screenshots need AI. Please paste the text.")
    result = rules_verdict(text)
    result.pop("details", None)
    result["mode"] = "rules"
    if ai_error:
        result["ai_error"] = ai_error
    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


@app.get("/api/health")
async def health():
    return {"ok": True, "ai": _ai_enabled(), "model": MODEL,
            "keys_total": len(key_pool), "keys_available": key_pool.available()}


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
async def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")))

"""HTTP API so apps such as NeuralLens can call the agent. Token-protected, local by default.

Example:
    python server.py                  # http://127.0.0.1:8080, this machine only
    python server.py --host 0.0.0.0   # reachable from a phone on the same network

    curl -X POST http://127.0.0.1:8080/v1/script \
      -H "X-Agent-Token: $AGENT_TOKEN" -H "Content-Type: application/json" \
      -d '{"notes": "Why agents fail...", "durationSeconds": 60}'
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from glasses_speaker_cue_agent import guardrails
from glasses_speaker_cue_agent.config import (
    MAX_MINUTES,
    MAX_NOTES_CHARS,
    MIN_MINUTES,
    ConfigError,
    load_settings,
)
from glasses_speaker_cue_agent.deck import DraftError
from glasses_speaker_cue_agent.pipeline import (
    CueRequest,
    UpstreamError,
    create_deck,
    quiet_sdk_logs,
)

MIN_TOKEN_CHARS = 24
MAX_BODY_BYTES = 64 * 1024
MAX_CONCURRENT = 2

_UPSTREAM_STATUS = {"rate_limited": 429}


class ScriptRequest(BaseModel):
    """Mirrors the fields of NeuralLens's ScriptGenerationRequest that the agent uses."""

    notes: str = Field(max_length=MAX_NOTES_CHARS)
    durationSeconds: int = Field(ge=round(MIN_MINUTES * 60), le=round(MAX_MINUTES * 60))
    language: str = "en"
    includeQa: bool = True


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def create_app(token: str) -> FastAPI:
    app = FastAPI(
        title="Glasses Speaker Cue Agent", docs_url=None, redoc_url=None, openapi_url=None
    )
    slots = asyncio.Semaphore(MAX_CONCURRENT)
    expected = token.encode()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Runs before the body is read, so unauthenticated or oversized
        # requests never reach validation or the model. Requiring
        # Content-Length rejects chunked uploads, whose size is unknown upfront.
        if request.url.path.startswith("/v1/"):
            sent = request.headers.get("x-agent-token", "").encode()
            if not hmac.compare_digest(sent, expected):
                return _error(401, "Missing or wrong X-Agent-Token.")
            length = request.headers.get("content-length", "")
            if request.method == "POST" and not length.isdigit():
                return _error(411, "Content-Length is required.")
            if length.isdigit() and int(length) > MAX_BODY_BYTES:
                return _error(413, "Request body too large.")
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/script")
    async def script(body: ScriptRequest):
        if slots.locked():
            return _error(429, "The agent is busy with other requests. Try again shortly.")
        async with slots:
            try:
                deck = await create_deck(
                    CueRequest(
                        notes=body.notes,
                        minutes=body.durationSeconds / 60,
                        language=body.language,
                        include_qa=body.includeQa,
                    )
                )
            except guardrails.InputError as exc:
                return _error(400, str(exc))
            except guardrails.BlockedError as exc:
                return _error(422, str(exc))
            except ConfigError:
                return _error(500, "The agent server is not configured. Check its .env.")
            except DraftError:
                return _error(502, "The model's reply could not be used. Try again.")
            except UpstreamError as exc:
                return _error(_UPSTREAM_STATUS.get(exc.kind, 502), str(exc))
        return deck.model_dump()

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="Default: this machine only.")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).with_name(".env"))
    token = os.environ.get("AGENT_TOKEN", "").strip()
    if len(token) < MIN_TOKEN_CHARS:
        print(
            f"Error: set AGENT_TOKEN in .env to a random value of at least {MIN_TOKEN_CHARS} "
            "characters, for example the output of:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"',
            file=sys.stderr,
        )
        return 2
    try:
        load_settings()
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    quiet_sdk_logs()
    if args.host != "127.0.0.1":
        print(
            "Listening beyond this machine. Use a trusted network (e.g. your phone's hotspot); "
            "find this laptop's IP with: ipconfig getifaddr en0",
            file=sys.stderr,
        )

    import uvicorn

    uvicorn.run(create_app(token), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

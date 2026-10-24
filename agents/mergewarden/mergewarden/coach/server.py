"""FastAPI app: WhatsApp simulator, public leaderboard and the Twilio webhook.

    python -m mergewarden.coach serve     # http://localhost:8090
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import config, whatsapp
from .guardrails import hash_user

log = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
NO_CACHE = {"Cache-Control": "no-cache"}  # always serve the latest simulator after an update
# Signs draft download links. Per process unless COACH_SALT is set, so old links expire on restart.
_LINK_KEY = (config.SALT or secrets.token_hex(32)).encode()


def file_token(path: str) -> str:
    rel = str(Path(path).resolve().relative_to(config.drafts_dir().resolve()))
    sig = hmac.new(_LINK_KEY, rel.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(rel.encode()).decode().rstrip("=") + "." + sig


def resolve_token(token: str) -> Path | None:
    try:
        b64, sig = token.rsplit(".", 1)
        rel = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    good = hmac.new(_LINK_KEY, rel.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig):
        return None
    base = config.drafts_dir().resolve()
    p = (base / rel).resolve()
    return p if base in p.parents and p.is_file() else None


def make_app(coach=None) -> FastAPI:
    app = FastAPI(title="Namma Commit", docs_url=None, redoc_url=None)

    def get_coach():
        nonlocal coach
        if coach is None:
            from .service import default_coach
            coach = default_coach()
        return coach

    def links(paths: list[str], base: str = "") -> list[dict]:
        return [{"name": Path(p).name, "url": f"{base}/files/{file_token(p)}"} for p in paths]

    @app.get("/", response_class=HTMLResponse)
    async def simulator():
        return FileResponse(STATIC / "simulator.html", headers=NO_CACHE)

    @app.get("/leaderboard", response_class=HTMLResponse)
    async def leaderboard_page():
        return FileResponse(STATIC / "leaderboard.html", headers=NO_CACHE)

    @app.get("/api/leaderboard")
    async def leaderboard():
        return {"leaderboard": get_coach().store.leaderboard(25)}

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz():
        return "ok"

    @app.post("/api/message")
    async def message(user_id: str = Form(..., max_length=80), text: str = Form("", max_length=4000),
                      audio: UploadFile | None = File(None)):
        data = mime = None
        if audio is not None:
            data = await audio.read(config.MAX_AUDIO_BYTES + 1)
            mime = (audio.content_type or "audio/webm").split(";")[0]
        reply = await get_coach().handle_message(f"sim:{user_id}", text=text or None, audio=data, mime=mime,
                                                 force_language=config.SIMULATOR_FORCE_LANGUAGE)
        out = reply.to_dict()
        out["attachments"] = links(reply.attachments)
        return JSONResponse(out)

    @app.post("/api/welcome")
    async def welcome(user_id: str = Form(..., max_length=80)):
        """Simulator: the onboarding questions for a brand-new student (null for returning ones)."""
        reply = await get_coach().welcome(f"sim:{user_id}", force_language=config.SIMULATOR_FORCE_LANGUAGE)
        return {"message": {**reply.to_dict(), "attachments": []} if reply else None}

    @app.get("/api/inbox")
    async def inbox(user_id: str):
        """Simulator: replies that arrived later (the gatekeeper review of the student's PR)."""
        replies = get_coach().pop_inbox(hash_user(f"sim:{user_id[:80]}"))
        return {"messages": [{**r.to_dict(), "attachments": links(r.attachments)} for r in replies]}

    @app.get("/files/{token}")
    async def draft_file(token: str):
        p = resolve_token(token)
        if not p:
            raise HTTPException(404)
        return PlainTextResponse(p.read_text(encoding="utf-8", errors="replace"),
                                 headers={"Content-Disposition": f'inline; filename="{p.name}"',
                                          "X-Content-Type-Options": "nosniff"})

    @app.post("/twilio/webhook")
    async def twilio_webhook(request: Request):
        form = await request.form()
        params = {k: str(v) for k, v in form.items()}
        url = (config.PUBLIC_BASE_URL + request.url.path) if config.PUBLIC_BASE_URL else str(request.url)
        if request.url.query:
            url += "?" + request.url.query
        if not whatsapp.valid_signature(config.TWILIO_AUTH_TOKEN, url, params,
                                        request.headers.get("X-Twilio-Signature", "")):
            log.warning("rejected Twilio webhook with invalid signature")
            raise HTTPException(403, "invalid signature")

        def as_text(reply) -> str:
            text = reply.text
            if reply.points_awarded:
                text += f"\n\n⭐ +{reply.points_awarded} points"
            if reply.badges:
                text += "\n🏅 " + ", ".join(reply.badges)
            if reply.attachments and config.PUBLIC_BASE_URL:
                text += "\n\n📄 " + "\n📄 ".join(f"{l['name']}: {l['url']}"
                                                for l in links(reply.attachments, config.PUBLIC_BASE_URL))
            return text

        async def respond(sender, body, audio, mime):
            async def later(reply):  # gatekeeper review results arrive after this webhook has returned
                await whatsapp.send_message(sender, as_text(reply))
            reply = await get_coach().handle_message(sender, text=body or None, audio=audio, mime=mime, notify=later)
            return as_text(reply)

        xml = await whatsapp.handle_webhook(params, respond)
        return Response(content=xml, media_type="application/xml")

    return app


def serve(host: str = "127.0.0.1", port: int | None = None) -> None:
    import uvicorn

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    uvicorn.run(make_app(), host=host, port=port or config.PORT)

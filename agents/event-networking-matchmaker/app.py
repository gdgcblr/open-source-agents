"""BuildBuddy: a small, self-hosted, evidence-based networking assistant."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time
import threading
from collections import defaultdict, deque

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from security import BodyLimitMiddleware

from importer import read_xlsx
from agent import run_agent
from nlp import LocalEncoder
from storage import Store, digest

ROOT = Path(__file__).resolve().parent
DEMO_EVENT = "BuildBuddy Sample Event"

class MatchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    window: str = Field(default="", max_length=100)
    active_only: bool = False
    use_ai: bool = False
    offered_only: bool = False

class CheckIn(BaseModel):
    spot: str = Field(max_length=100)
    minutes: int = Field(default=15, ge=5, le=60)

def create_app(db_path=None, admin_key=None, demo=False, clock=time.time, encoder=None):
    db_path = Path(db_path or os.getenv("BUILDBUDDY_DB", ROOT / "data/buildbuddy.sqlite3"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(db_path)
    admin_key = admin_key or os.getenv("BUILDBUDDY_ADMIN_KEY") or secrets.token_urlsafe(24)
    app = FastAPI(title="BuildBuddy", version="2.0.0")
    encoder = encoder if encoder is not None else LocalEncoder()
    app.state.admin_key, app.state.store = admin_key, store
    app.state.encoder = encoder
    attempts, lock = defaultdict(deque), threading.Lock()
    if demo:
        profiles, _ = read_xlsx((ROOT / "sample/form-responses.xlsx").read_bytes())
        store.import_event(DEMO_EVENT, ["Table A", "Table B", "Community desk"], profiles, demo=True)

    @app.middleware("http")
    async def safeguards(request, call_next):
        # Same-origin browser requests; never accept cross-origin writes or model calls.
        origin = request.headers.get("origin")
        expected_origin = os.getenv("BUILDBUDDY_PUBLIC_URL", str(request.base_url)).rstrip("/")
        if origin and origin.rstrip("/") != expected_origin:
            return JSONResponse({"detail": "Cross-origin requests are disabled."}, status_code=403)
        try:
            size = int(request.headers.get("content-length", "0") or 0)
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
        if size > 6 * 1024 * 1024:
            return JSONResponse({"detail": "Request exceeds 6 MB."}, status_code=413)
        if request.url.path == "/api/import" and not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + admin_key):
            return JSONResponse({"detail": "Organizer key required."}, status_code=401)
        if request.url.path.startswith("/api"):
            # Separate authenticated sessions sharing the venue's single public IP.
            host = digest(request.headers["authorization"]) if request.headers.get("authorization") else (request.client.host if request.client else "unknown")
            with lock:
                now = clock()
                # Evict idle clients so limiter memory is bounded by recent traffic.
                for key in list(attempts):
                    if not attempts[key] or attempts[key][-1] < now - 60:
                        del attempts[key]
                if host not in attempts and len(attempts) >= 10000:
                    return JSONResponse({"detail": "Server is busy. Try again shortly."}, status_code=429)
                queue = attempts[host]
                while queue and queue[0] < now - 60:
                    queue.popleft()
                if len(queue) >= 120:
                    return JSONResponse({"detail": "Too many requests. Try again in a minute."}, status_code=429)
                queue.append(now)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def bearer(request):
        return request.headers.get("authorization", "").removeprefix("Bearer ")

    def admin(request):
        if not secrets.compare_digest(bearer(request), admin_key):
            raise HTTPException(401, "Organizer key required.")

    def attendee(event, request):
        person = store.authenticate(event, bearer(request))
        if not person:
            raise HTTPException(401, "Invalid private access token for this event.")
        return person

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/api/config")
    def config():
        return {"demo": demo, "demo_event": DEMO_EVENT if demo else None,
                "ai_available": bool(os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL")),
                "semantic_available":encoder.available,"engine":"Local semantic NLP" if encoder.available else "Local lexical NLP",
                "model":"all-MiniLM-L6-v2" if encoder.available else None,"warning":encoder.error}

    @app.get("/api/events")
    def events():
        with store.connect() as db:
            return [{"name": r["name"], "spots": json.loads(r["spots"])} for r in db.execute("SELECT * FROM events ORDER BY name")]

    @app.get("/api/demo")
    def demo_profiles():
        if not demo:
            raise HTTPException(404, "Sample mode is disabled.")
        return [{"id": p["id"], "name": p["name"], "token": f"demo-{p['id']}"} for p in store.people(DEMO_EVENT)]

    @app.post("/api/import")
    def import_event(request: Request, event: str = Form(...), spots: str = Form(...), file: UploadFile = File(...)):
        admin(request)
        event = event.strip()
        locations = [x.strip() for x in spots.split(",") if x.strip()]
        if not event or len(event) > 100 or not 1 <= len(locations) <= 10 or any(len(x) > 100 for x in locations):
            raise HTTPException(400, "Provide an event name (up to 100 characters) and 1–10 comma-separated meeting spots.")
        if event == DEMO_EVENT:
            raise HTTPException(400, "This event name is reserved for fictional sample data.")
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(400, "Upload an .xlsx file.")
        try:
            profiles, skipped = read_xlsx(file.file.read(5 * 1024 * 1024 + 1))
        except Exception as exc:
            raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else "Unable to read this workbook. Check the XLSX format.") from exc
        if not profiles:
            raise HTTPException(400, "No consenting profiles found. Existing event data was not changed.")
        credentials, imported = store.import_event(event, list(dict.fromkeys(locations)), profiles)
        return {"imported": imported, "skipped": skipped + len(profiles) - imported, "credentials": credentials,
                "note": "This is a full event snapshot. Removed/opted-out attendees were deleted; previous withdrawals stay excluded. Existing tokens are unchanged. New private tokens are shown only now."}

    @app.get("/api/me")
    def me(event: str, request: Request):
        p = attendee(event, request)
        return {k: v for k, v in p.items() if k not in {"token_hash"}}

    @app.post("/api/matches")
    def matches(payload: MatchRequest, event: str, request: Request):
        me = attendee(event, request)
        people = store.people(event)
        with store.connect() as db:
            excluded = {r[0] for r in db.execute("SELECT target FROM met WHERE event=? AND viewer=?", (event, me["id"]))}
        result=run_agent(me,people,payload.query,payload.window,excluded,payload.active_only,clock(),encoder,payload.use_ai,payload.offered_only)
        # Recheck authorization and eligible identities after potentially slow model work.
        # A concurrent withdrawal/import must not leak a now-removed profile.
        attendee(event,request)
        fresh={p["id"]:p for p in store.people(event)}
        result["matches"]=[p for p in result["matches"] if p["id"] in fresh and
                           all(p[k]==fresh[p["id"]][k] for k in ("name","offers","needs","interests","project","window"))]
        for p in result["matches"]:
            live=fresh[p["id"]]
            active=live["until_ts"]>clock()
            p.update({"spot":live["spot"] if active else None,"until_ts":live["until_ts"] if active else None,"checked_at":live["checked_at"] if active else None})
        if payload.active_only:
            result["matches"]=[p for p in result["matches"] if p["spot"]]
        return result

    @app.get("/api/admin/events")
    def admin_events(request: Request):
        admin(request)
        with store.connect() as db:
            return [dict(r) for r in db.execute("SELECT e.name,COUNT(p.id) AS attendees FROM events e LEFT JOIN people p ON e.name=p.event GROUP BY e.name ORDER BY e.name")]

    @app.delete("/api/admin/event")
    def delete_event(event: str, request: Request):
        admin(request)
        if event==DEMO_EVENT and demo:
            raise HTTPException(400,"Sample data is managed by sample mode. Use a separate database for real events.")
        with store.connect() as db:
            db.execute("DELETE FROM events WHERE name=?",(event,))
            db.execute("DELETE FROM withdrawals WHERE event=?",(event,))
        return {"ok":True,"message":"Event profiles, check-ins, met history and withdrawal markers removed."}

    @app.post("/api/checkin")
    def checkin(payload: CheckIn, event: str, request: Request):
        p = attendee(event, request)
        with store.connect() as db:
            spots = json.loads(db.execute("SELECT spots FROM events WHERE name=?", (event,)).fetchone()[0])
            if payload.spot not in spots:
                raise HTTPException(400, "Choose a configured meeting spot.")
            now = clock()
            db.execute("UPDATE people SET spot=?,until_ts=?,checked_at=? WHERE event=? AND id=?",
                       (payload.spot, now + payload.minutes * 60, now, event, p["id"]))
        return {"ok": True}

    @app.delete("/api/checkin")
    def checkout(event: str, request: Request):
        p = attendee(event, request)
        with store.connect() as db:
            db.execute("UPDATE people SET spot='',until_ts=0,checked_at=0 WHERE event=? AND id=?", (event, p["id"]))
        return {"ok": True}

    @app.post("/api/met/{target}")
    def mark_met(target: str, event: str, request: Request):
        p = attendee(event, request)
        with store.connect() as db:
            if target == p["id"] or not db.execute("SELECT 1 FROM people WHERE event=? AND id=?", (event, target)).fetchone():
                raise HTTPException(400, "Choose another attendee in this event.")
            db.execute("INSERT OR IGNORE INTO met VALUES(?,?,?)", (event, p["id"], target))
        return {"ok": True}

    @app.delete("/api/met")
    def reset_met(event: str, request: Request):
        p = attendee(event, request)
        with store.connect() as db:
            db.execute("DELETE FROM met WHERE event=? AND viewer=?", (event, p["id"]))
        return {"ok": True}

    @app.delete("/api/me")
    def withdraw(event: str, request: Request):
        p = attendee(event, request)
        with store.connect() as db:
            db.execute("INSERT OR IGNORE INTO withdrawals VALUES(?,?)", (event, p["id"]))
            db.execute("DELETE FROM people WHERE event=? AND id=?", (event, p["id"]))
        return {"ok": True, "message": "Profile removed. This attendee ID remains excluded from future imports for this event."}

    @app.post("/api/admin/rotate/{attendee_id}")
    def rotate(attendee_id: str, event: str, request: Request):
        admin(request)
        new_token = secrets.token_urlsafe(24)
        with store.connect() as db:
            changed = db.execute("UPDATE people SET token_hash=? WHERE event=? AND id=?", (digest(new_token), event, attendee_id.upper()))
            if changed.rowcount != 1:
                raise HTTPException(404, "Attendee not found.")
        return {"id": attendee_id.upper(), "token": new_token}

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=[x.strip() for x in os.getenv("BUILDBUDDY_ALLOWED_HOSTS","localhost,127.0.0.1").split(",") if x.strip()])
    return app

if __name__ == "__main__":
    import uvicorn
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Load clearly labeled fictional profiles and public sample login tokens")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    application = create_app(demo=args.demo)
    print(f"BuildBuddy: http://{args.host}:{args.port}\nOrganizer key (keep private): {application.state.admin_key}")
    uvicorn.run(application, host=args.host, port=args.port, access_log=False)

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .catalog import COUNTRIES
from .models import EntryInput, TripRequest, Itinerary, validate_itinerary
from .storage import Store
from .agents import plan_trip
from .progress import STAGES, timestamp, mark_stage, finish_run

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def create_app(runtime: Path | None = None):
    store = Store(runtime or ROOT / ".runtime")
    tasks = set()

    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("TRAVELOGUE_MODE", "demo") != "demo":
            raise RuntimeError("Firebase/Neon integrations are not implemented yet. Use local demo mode.")
        # Previous process cannot resume in-memory inference tasks.
        with store.connection() as db:
            rows = list(db.execute("SELECT id,payload FROM runs"))
        for row in rows:
            run = json.loads(row["payload"])
            if run["status"] in {"queued", "running"}:
                finish_run(run, "failed", "The server restarted. Please retry the plan.")
                store.put_json("runs", row["id"], run)
        yield
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Travelogue", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Single-user demo is deliberately not a deployable authenticated backend.
        allowed = {"localhost", "127.0.0.1", "::1", "testserver"}
        if request.url.hostname not in allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "This milestone runs locally only."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Origin is not permitted."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "storage": "local SQLite demo", "provider": os.getenv("MODEL_PROVIDER", "demo"),
                "model": os.getenv("OLLAMA_MODEL", "gemma3:4b"), "public_sharing": False}

    @app.get("/api/model/status")
    async def model_status():
        model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        if os.getenv("MODEL_PROVIDER", "demo") != "ollama":
            return {"available": False, "provider": "demo", "message": "Scripted demo. Set MODEL_PROVIDER=ollama to run local Gemma."}
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/tags")
                r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            available = model in names
            return {"available": available, "provider": "ollama", "model": model,
                    "message": "Ready for local inference." if available else f"Download the configured model on the host: ollama pull {model}"}
        except (httpx.HTTPError, ValueError, KeyError):
            return {"available": False, "provider": "ollama", "model": model,
                    "message": "Ollama is unreachable. Start Ollama on the host and check OLLAMA_BASE_URL."}

    @app.get("/api/catalog")
    async def catalog():
        return {"countries": COUNTRIES, "warning": "Curated workshop guidance is unverified; consult official sources."}

    @app.get("/api/entries")
    async def entries():
        return store.entries()

    @app.post("/api/entries", status_code=201)
    async def add_entry(data: EntryInput):
        if data.published:
            raise HTTPException(400, "Public sharing requires the future authenticated integration.")
        return store.save_entry(data)

    @app.put("/api/entries/{ident}")
    async def edit_entry(ident: str, data: EntryInput):
        if not store.entry(ident):
            raise HTTPException(404, "Memory not found.")
        if data.published:
            raise HTTPException(400, "Public sharing is disabled in the local demo.")
        return store.save_entry(data, ident)

    @app.delete("/api/entries/{ident}", status_code=204)
    async def delete_entry(ident: str):
        if not store.entry(ident):
            raise HTTPException(404, "Memory not found.")
        store.delete_entry(ident)

    @app.post("/api/entries/{ident}/media", status_code=201)
    async def upload_media(ident: str, file: UploadFile = File(...)):
        if not store.entry(ident):
            raise HTTPException(404, "Memory not found.")
        key = str(uuid.uuid4())
        path = store.root / "media" / key
        limit = 25 * 1024 * 1024
        size = 0
        try:
            with path.open("wb") as target:
                while chunk := await file.read(65536):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "Maximum upload size is 25 MB.")
                    target.write(chunk)
            with path.open("rb") as src:
                head = src.read(32)
            mime = None
            if head.startswith(b"\xff\xd8\xff"):
                mime = "image/jpeg"
            elif head.startswith(b"\x89PNG\r\n\x1a\n"):
                mime = "image/png"
            elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                mime = "image/webp"
            elif head[4:8] == b"ftyp":
                mime = "video/mp4"
            elif head.startswith(b"\x1aE\xdf\xa3"):
                mime = "video/webm"
            if not mime:
                raise HTTPException(415, "Use a JPEG, PNG, WebP image or MP4/WebM video.")
            if mime.startswith("image") and size > 10 * 1024 * 1024:
                raise HTTPException(413, "Images must be at most 10 MB.")
            if not shutil.which("ffprobe"):
                raise HTTPException(503, "Install FFprobe on the application host to validate media.")
            try:
                result = await asyncio.to_thread(subprocess.run, ["ffprobe", "-v", "error", "-show_entries",
                    "format=duration:stream=codec_type", "-of", "json", str(path)],
                    capture_output=True, text=True, timeout=10, check=True)
                info = json.loads(result.stdout)
                if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
                    raise ValueError("No visual media stream")
                if mime.startswith("video") and not 0 < float(info.get("format", {}).get("duration", 0)) <= 30:
                    raise ValueError("Video must be at most 30 seconds")
            except (subprocess.SubprocessError, ValueError, KeyError) as exc:
                raise HTTPException(422, "Media is corrupt or the video exceeds 30 seconds.") from exc
            name = Path(file.filename or "attachment").name[:160]
            with store.connection() as db:
                db.execute("INSERT INTO media VALUES (?,?,?,?)", (key, ident, name, mime))
            return {"id": key, "entry_id": ident, "filename": name, "mime": mime}
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get("/api/media/{ident}")
    async def get_media(ident: str):
        with store.connection() as db:
            row = db.execute("SELECT * FROM media WHERE id=?", (ident,)).fetchone()
        if not row or not (store.root / "media" / ident).is_file():
            raise HTTPException(404, "Attachment not found.")
        return FileResponse(store.root / "media" / ident, media_type=row["mime"], headers={"Cache-Control": "no-store"})

    @app.delete("/api/media/{ident}", status_code=204)
    async def delete_media(ident: str):
        with store.connection() as db:
            if not db.execute("SELECT 1 FROM media WHERE id=?", (ident,)).fetchone():
                raise HTTPException(404, "Attachment not found.")
            db.execute("DELETE FROM media WHERE id=?", (ident,))
        (store.root / "media" / ident).unlink(missing_ok=True)

    async def execute_run(ident: str, trip: TripRequest):
        run = store.get_json("runs", ident)
        def progress(stage, status="running", metrics=None):
            mark_stage(run, stage, status)
            if metrics is not None:
                run.setdefault("model_timings", []).append(metrics)
            store.put_json("runs", ident, run)
        try:
            async with asyncio.timeout(float(os.getenv("PLANNER_TIMEOUT_SECONDS", "120"))):
                result = await plan_trip(trip, run["provider"], progress)
            run["result"] = result
            finish_run(run, "completed")
        except asyncio.CancelledError:
            finish_run(run, "failed", "Server stopped. Retry the plan.")
            raise
        except TimeoutError:
            finish_run(run, "failed", "Planning reached its deadline. Your local model may need more time; retry with fewer days or increase PLANNER_TIMEOUT_SECONDS on the host.")
        except ValueError as exc:
            message = str(exc)
            finish_run(run, "failed", message if message.startswith(("Itinerary rejected:", "Configuration error:")) else
                       "The model returned an invalid itinerary. Try a shorter trip or revise your preferences.")
        except Exception:
            # Avoid returning provider responses, credentials, prompts, or filesystem paths.
            finish_run(run, "failed", "Planning failed. Check Ollama availability and model configuration. No demo output was substituted.")
        finally:
            store.put_json("runs", ident, run)

    @app.post("/api/planner/runs", status_code=202)
    async def start_run(trip: TripRequest):
        if tasks:
            raise HTTPException(429, "A plan is already running. Wait for it to finish.")
        provider = os.getenv("MODEL_PROVIDER", "demo")
        if provider not in {"demo", "ollama"}:
            raise HTTPException(503, "MODEL_PROVIDER must be demo or ollama.")
        ident = str(uuid.uuid4())
        run = {"id": ident, "status": "queued", "stage": "queued", "stages": [], "provider": provider,
               "stage_states": {name: "pending" for name in STAGES}, "started_at": timestamp(),
               "updated_at": timestamp(), "deadline_seconds": float(os.getenv("PLANNER_TIMEOUT_SECONDS", "120")),
               "request": trip.model_dump(mode="json")}
        store.put_json("runs", ident, run)
        task = asyncio.create_task(execute_run(ident, trip))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return run

    @app.get("/api/planner/runs/{ident}")
    async def get_run(ident: str):
        run = store.get_json("runs", ident)
        if not run:
            raise HTTPException(404, "Planning run not found.")
        return run

    @app.post("/api/plans/{run_id}", status_code=201)
    async def save_plan(run_id: str, edited: Itinerary | None = Body(default=None)):
        run = store.get_json("runs", run_id)
        if not run or run["status"] != "completed":
            raise HTTPException(400, "Only a completed plan can be saved.")
        if edited:
            errors = validate_itinerary(edited, TripRequest.model_validate(run["request"]),
                                        {s["id"] for s in run["result"]["sources"]})
            if errors:
                raise HTTPException(422, " ".join(errors))
            run["result"]["itinerary"] = edited.model_dump(mode="json")
            run["result"]["estimated_total"] = str(sum(a.estimate for d in edited.days for a in d.activities))
        store.put_json("saved_plans", run_id, run)
        return run

    @app.get("/api/plans")
    async def saved_plans():
        return store.saved()

    if (ROOT / "dist").is_dir():
        app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
    return app


app = create_app()

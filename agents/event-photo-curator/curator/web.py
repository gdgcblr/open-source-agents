"""Single-event laptop pilot. All data and face matching stay on loopback."""

from io import BytesIO
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import tempfile
import zipfile
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import imagehash
from PIL import Image
from pydantic import BaseModel, Field
from rich.console import Console
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import PhotoAgent, visual_assessment
from .dedupe import group_duplicates, select_diverse
from .exports import export_jpeg
from .faces import FaceMatcher, match_faces
from .filters import exposure_flag, sharpness
from .loader import Photo, SUPPORTED, load_image, normalize, read_photo
from .providers import MockProvider, OllamaProvider
from .ranker import rank

MAX_FILE = 100 * 1024 * 1024


class CurateRequest(BaseModel):
    top: int = Field(default=15, ge=1, le=1000)
    provider: str = Field(default="ollama", pattern="^(ollama|mock)$")
    model: str = Field(default="gemma4:e2b-it-q4_K_M", max_length=100)
    max_minutes: int = Field(default=30, ge=1, le=120)
    caption_style: str = Field(
        default="GDG Cloud Bengaluru Instagram, casual, no hashtag spam", max_length=500
    )


class AgentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    model: str = Field(default="gemma4:e2b-it-q4_K_M", max_length=100)
    max_minutes: int = Field(default=10, ge=1, le=30)


class ImportRequest(BaseModel):
    directory: str = Field(min_length=1, max_length=4096)
    photographer: str = Field(min_length=1, max_length=100)
    permission: bool = False


def create_app(data: Path) -> FastAPI:
    data = data.resolve()
    if data == Path.cwd().resolve() or data == Path(data.anchor):
        raise ValueError(
            "Choose a dedicated --data folder, not the project or filesystem root."
        )
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    data.chmod(0o700)
    for directory in ("originals", "thumbs", "previews", "cache"):
        (data / directory).mkdir(parents=True, exist_ok=True)
    database = data / "event.sqlite3"
    lock, face_lock = threading.RLock(), threading.Lock()
    cancel = threading.Event()
    agent_result = {"answer": "", "photos": [], "trace": [], "tokens": 0, "steps": 0}
    session = secrets.token_urlsafe(32)
    job = {
        "running": False,
        "phase": "ready",
        "reviewed": 0,
        "total": 0,
        "tokens": 0,
        "cache_hits": 0,
        "error": "",
    }

    def connect():
        db = sqlite3.connect(database)
        db.row_factory = sqlite3.Row
        return db

    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, original TEXT NOT NULL,
            photographer TEXT NOT NULL, role TEXT NOT NULL, sharpness REAL NOT NULL,
            exposure TEXT NOT NULL, phash TEXT NOT NULL, flags TEXT NOT NULL,
            assessment TEXT NOT NULL DEFAULT '{}', picked INTEGER NOT NULL DEFAULT 0,
            faces TEXT, width INTEGER NOT NULL, height INTEGER NOT NULL)""")

    app = FastAPI(
        title="AfterClick, local pilot",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(
                request.cookies.get("curator_session", ""), session
            ):
                return JSONResponse(
                    {"detail": "Open the gallery on this laptop first."},
                    status_code=403,
                )
            if request.method != "GET":
                origin = request.headers.get("origin")
                if (
                    origin
                    and origin
                    != f'{request.url.scheme}://{request.headers.get("host")}'
                ):
                    return JSONResponse(
                        {"detail": "Cross-origin request blocked."}, status_code=403
                    )
                if request.headers.get("x-curator-request") != "local":
                    return JSONResponse(
                        {"detail": "Missing local request header."}, status_code=403
                    )
                try:
                    if (
                        int(request.headers.get("content-length", 0))
                        > 500 * 1024 * 1024
                    ):
                        return JSONResponse(
                            {"detail": "Upload at most 500 MB per batch."},
                            status_code=413,
                        )
                except ValueError:
                    return JSONResponse(
                        {"detail": "Invalid content length."}, status_code=400
                    )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/") and not request.url.path.endswith(
            ("/thumb", "/preview")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/organizer", response_class=HTMLResponse)
    @app.get("/attendee", response_class=HTMLResponse)
    @app.get("/", response_class=HTMLResponse)
    def index():
        response = HTMLResponse(
            (Path(__file__).parent / "static/index.html").read_text()
        )
        response.set_cookie(
            "curator_session", session, httponly=True, samesite="strict"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )

    def public(row):
        return {
            key: row[key]
            for key in (
                "id",
                "filename",
                "photographer",
                "role",
                "sharpness",
                "exposure",
                "picked",
                "width",
                "height",
            )
        } | {
            "flags": json.loads(row["flags"]),
            "assessment": json.loads(row["assessment"]),
        }

    @app.get("/api/runtime")
    def runtime():
        from .runtime import runtime_status

        return runtime_status()

    @app.get("/api/state")
    def state():
        with connect() as db:
            count = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            picked = db.execute(
                "SELECT COUNT(*) FROM photos WHERE picked=1"
            ).fetchone()[0]
        return {"count": count, "picked": picked, "job": job.copy(), "local_only": True}

    @app.get("/api/photos")
    def photos(offset: int = 0, limit: int = 48, best: bool = False):
        if not 0 <= offset or not 1 <= limit <= 100:
            raise HTTPException(400, "Invalid page")
        with connect() as db:
            where = "WHERE picked=1" if best else ""
            rows = db.execute(
                f"SELECT * FROM photos {where} ORDER BY picked DESC, filename, id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return {"photos": [public(r) for r in rows], "next_offset": offset + len(rows)}

    def import_files(
        files, photographer, role="attendee", permission=False, during_import=False
    ):
        if not photographer.strip():
            raise HTTPException(400, "Add a photographer credit.")
        if not permission:
            raise HTTPException(400, "Confirm permission to add these event photos.")
        if role not in ("organizer", "attendee") or len(files) > 100:
            raise HTTPException(
                400, "Choose a valid uploader role and at most 100 files."
            )
        with lock:
            if job["running"] and not during_import:
                raise HTTPException(
                    409, "Wait for the current job before adding photos."
                )
            with connect() as db:
                current_count = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            if current_count + len(files) > 500:
                raise HTTPException(
                    400,
                    "This laptop pilot allows at most 500 photos per event. Use a smaller batch or a separate event folder.",
                )
            added, errors = [], []
            # One original is decoded at a time; thumbnails are generated once.
            for upload_file in files:
                filename = Path((upload_file.filename or "").replace("\\", "/")).name
                suffix = Path(filename).suffix.lower()
                if suffix not in SUPPORTED:
                    errors.append(f"{filename}: unsupported format")
                    upload_file.file.close()
                    continue
                payload = upload_file.file.read(MAX_FILE + 1)
                upload_file.file.close()
                if not payload or len(payload) > MAX_FILE:
                    errors.append(f"{filename}: empty or larger than 100 MB")
                    continue
                temporary = data / "originals" / (uuid4().hex + suffix)
                temporary.write_bytes(payload)
                try:
                    photo, image = read_photo(temporary)
                    if image is None:
                        errors.append(f"{filename}: " + "; ".join(photo.reasons))
                        continue
                    with lock, connect() as db:
                        if db.execute(
                            "SELECT 1 FROM photos WHERE id=?", (photo.digest,)
                        ).fetchone():
                            errors.append(f"{filename}: already in this event")
                            continue
                        sharp = sharpness(image)
                        exposure = exposure_flag(image, 20)
                        flags = (
                            [f"Soft image: sharpness {sharp:.1f}"]
                            if sharp < 100
                            else []
                        ) + ([exposure] if exposure else [])
                        original = photo.digest + suffix
                        (data / "originals" / original).write_bytes(payload)
                        (data / "previews" / f"{photo.digest}.jpg").write_bytes(
                            photo.preview
                        )
                        db.execute(
                            """INSERT INTO photos
                            (id,filename,original,photographer,role,sharpness,exposure,phash,flags,width,height)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                photo.digest,
                                filename,
                                original,
                                photographer.strip(),
                                role,
                                sharp,
                                exposure,
                                str(imagehash.phash(image)),
                                json.dumps(flags),
                                image.width,
                                image.height,
                            ),
                        )
                        added.append(photo.digest)
                finally:
                    temporary.unlink(missing_ok=True)
            return {"added": added, "errors": errors}

    @app.post("/api/upload")
    def upload(
        files: list[UploadFile] = File(),
        photographer: str = Form(min_length=1, max_length=100),
        role: str = Form(default="attendee"),
        permission: bool = Form(default=False),
    ):
        return import_files(files, photographer, role, permission)

    @app.post("/api/import")
    def import_directory(options: ImportRequest):
        if not options.permission or not options.photographer.strip():
            raise HTTPException(
                400, "Confirm photo permission and add a photographer credit."
            )
        folder = Path(options.directory).expanduser().resolve()
        if (
            not folder.is_dir()
            or folder == Path(folder.anchor)
            or folder.is_relative_to(data)
        ):
            raise HTTPException(
                400, "Choose an existing photo directory outside event storage."
            )
        paths = []
        for path in folder.rglob("*"):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix.lower() in SUPPORTED
            ):
                resolved = path.resolve()
                if resolved.is_relative_to(folder) and not resolved.is_relative_to(
                    data
                ):
                    paths.append(path)
                if len(paths) > 500:
                    raise HTTPException(400, "Import at most 500 photos at a time.")
        if not paths:
            raise HTTPException(400, "No supported photos found in this directory.")

        def run_import():
            deadline = time.monotonic() + 600
            try:
                for index, path in enumerate(sorted(paths)):
                    if cancel.is_set() or time.monotonic() > deadline:
                        job.update(
                            phase="Import stopped; imported copies remain available"
                        )
                        return
                    job.update(phase=f"Importing {index+1}/{len(paths)}")
                    with path.open("rb") as stream:
                        result = import_files(
                            [UploadFile(filename=path.name, file=stream)],
                            options.photographer,
                            "organizer",
                            True,
                            True,
                        )
                    job["added"] += len(result["added"])
                    job["errors"].extend(result["errors"])
                    job["reviewed"] = index + 1
                job.update(
                    phase=f"Imported {job['added']} photos; {len(job['errors'])} skipped"
                )
            except Exception:
                job.update(
                    error="Directory import failed. Imported copies remain; originals were not changed."
                )
            finally:
                job["running"] = False

        with lock:
            if job["running"]:
                raise HTTPException(409, "A job is already running.")
            cancel.clear()
            job.update(
                running=True,
                kind="import",
                phase="Reading directory",
                total=len(paths),
                reviewed=0,
                added=0,
                errors=[],
                error="",
                tokens=0,
                cache_hits=0,
            )
            threading.Thread(target=run_import, daemon=True).start()
        return {"started": True, "total": len(paths)}

    def get_photo(photo_id):
        with connect() as db:
            row = db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Photo not found")
        return row

    def display_image(photo_id: str, max_edge: int, quality: int):
        row = get_photo(photo_id)
        target = data / "thumbs" / f'{row["id"]}-{max_edge}-v2.webp'
        with lock:
            if not target.exists():
                try:
                    image = load_image(data / "originals" / row["original"], max_edge)
                    clean = Image.new("RGB", image.size)
                    clean.paste(image)
                    temporary = target.with_name(uuid4().hex + ".webp")
                    try:
                        clean.save(temporary, "WEBP", quality=quality)
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
                except Exception:
                    raise HTTPException(
                        422,
                        "Cannot generate this preview. Download the original instead.",
                    ) from None
        return FileResponse(
            target,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=86400, immutable"},
        )

    @app.get("/api/photos/{photo_id}/thumb")
    def thumbnail(photo_id: str):
        return display_image(photo_id, 1024, 88)

    @app.get("/api/photos/{photo_id}/preview")
    def display_preview(photo_id: str):
        return display_image(photo_id, 2048, 90)

    @app.get("/api/photos/{photo_id}/original")
    def original(photo_id: str):
        row = get_photo(photo_id)
        return FileResponse(
            data / "originals" / row["original"],
            filename=row["filename"],
            media_type="application/octet-stream",
        )

    @app.get("/api/photos/{photo_id}/export")
    def derivative(photo_id: str, watermark: str = "", metadata: bool = True):
        if len(watermark) > 120:
            raise HTTPException(400, "Watermark is limited to 120 characters")
        row = get_photo(photo_id)
        try:
            payload = export_jpeg(
                data / "originals" / row["original"],
                row["photographer"] if metadata else "",
                watermark,
            )
        except (ValueError, OSError, ImportError):
            raise HTTPException(
                422,
                "Cannot export this format as JPEG. The untouched original is still downloadable.",
            ) from None
        return Response(
            payload,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": 'attachment; filename="attributed-photo.jpg"'
            },
        )

    def curate(options):
        try:
            with connect() as db:
                rows = db.execute(
                    "SELECT * FROM photos ORDER BY filename, id"
                ).fetchall()
            records = []
            for row in rows:
                records.append(
                    Photo(
                        path=data / "originals" / row["original"],
                        digest=row["id"],
                        preview=(data / "previews" / f'{row["id"]}.jpg').read_bytes(),
                        sharpness=row["sharpness"],
                        exposure=row["exposure"],
                        phash=imagehash.hex_to_hash(row["phash"]),
                        flags=json.loads(row["flags"]),
                    )
                )
            records.sort(key=lambda p: (bool(p.flags), -p.sharpness, p.digest))
            group_duplicates(records, 6)
            provider = (
                MockProvider()
                if options.provider == "mock"
                else OllamaProvider(options.model)
            )
            if len(records) > 500:
                raise ValueError(
                    "This laptop pilot reviews at most 500 photos per event. Split larger events before starting."
                )
            deadline = time.monotonic() + options.max_minutes * 60
            job.update(phase=f"Reviewing with {provider.model}", total=len(records))
            for photo in records:
                if cancel.is_set() or time.monotonic() >= deadline:
                    job.update(
                        running=False,
                        phase="Stopped; completed scores are cached, previous picks remain available",
                    )
                    return
                used, hits = rank(
                    [photo],
                    provider,
                    options.caption_style,
                    data / "cache",
                    1,
                    Console(quiet=True),
                )
                with connect() as db:
                    db.execute(
                        "UPDATE photos SET assessment=? WHERE id=?",
                        (json.dumps(photo.assessment), photo.digest),
                    )
                job.update(
                    reviewed=job["reviewed"] + 1,
                    tokens=job["tokens"] + used,
                    cache_hits=job["cache_hits"] + hits,
                )
            picked_ids = {p.digest for p in select_diverse(records, options.top)}
            with connect() as db:
                db.execute("UPDATE photos SET picked=0")
                db.executemany(
                    "UPDATE photos SET picked=1 WHERE id=?", [(i,) for i in picked_ids]
                )
            job.update(
                phase=f"Complete: {len(picked_ids)} diverse picks", running=False
            )
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, (RuntimeError, ValueError))
                else "Review failed; previous picks remain available. Retry to use completed cached scores."
            )
            job.update(running=False, phase="Review stopped", error=message)

    @app.post("/api/curate")
    def start_curate(options: CurateRequest):
        with lock:
            if job["running"]:
                raise HTTPException(409, "A review is already running")
            cancel.clear()
            job.update(
                running=True,
                kind="review",
                reviewed=0,
                total=0,
                tokens=0,
                cache_hits=0,
                error="",
            )
            threading.Thread(target=curate, args=(options,), daemon=True).start()
        return {"started": True}

    @app.post("/api/cancel")
    def cancel_review():
        cancel.set()
        return {"note": "Stopping after the current image finishes."}

    @app.get("/api/picks.zip")
    def download_picks():
        with connect() as db:
            rows = db.execute(
                "SELECT * FROM photos WHERE picked=1 ORDER BY filename, id"
            ).fetchall()
        if not rows:
            raise HTTPException(400, "Run curation before downloading picks.")
        handle = tempfile.NamedTemporaryFile(
            dir=data / "cache", suffix=".zip", delete=False
        )
        path = Path(handle.name)
        handle.close()
        try:
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                for row in rows:
                    archive.write(
                        data / "originals" / row["original"],
                        row["id"][:8] + "-" + row["filename"],
                    )
            return FileResponse(
                path,
                filename="event-picks.zip",
                background=BackgroundTask(path.unlink, missing_ok=True),
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/match")
    def match(
        files: list[UploadFile] = File(),
        consent: bool = Form(default=False),
        team: bool = Form(default=False),
        threshold: float = Form(default=0.45),
        mode: str = Form(default="event"),
    ):
        if mode not in ("event", "pair") or (
            mode == "pair" and (len(files) != 2 or team)
        ):
            raise HTTPException(
                400, "Pair comparison requires exactly two single-face photos."
            )
        if not consent:
            raise HTTPException(
                400, "Face matching requires explicit consent for the reference photos."
            )
        if not 0.3 <= threshold <= 0.9 or not 1 <= len(files) <= 10:
            raise HTTPException(
                400, "Use 1–10 references and a threshold between 0.3 and 0.9."
            )
        if not face_lock.acquire(blocking=False):
            raise HTTPException(
                409, "A face search is already running. Wait for it to finish."
            )
        try:
            try:
                matcher = FaceMatcher(Path.cwd() / ".cache/models")
            except ValueError as exc:
                raise HTTPException(503, str(exc)) from None
            references = []
            for file in files:
                payload = file.file.read(10 * 1024 * 1024 + 1)
                file.file.close()
                if len(payload) > 10 * 1024 * 1024:
                    raise HTTPException(
                        413, "Reference photos must be smaller than 10 MB."
                    )
                try:
                    with Image.open(BytesIO(payload)) as image:
                        embeddings = matcher.encode(normalize(image, 2048))
                except Exception:
                    raise HTTPException(
                        400, "Cannot decode a reference photo."
                    ) from None
                if not embeddings:
                    raise HTTPException(
                        400,
                        "No clear face in a reference. Try a front-facing, well-lit image.",
                    )
                if not team and len(embeddings) != 1:
                    raise HTTPException(
                        400,
                        "For personal search, use a reference with exactly one face.",
                    )
                references.extend(embeddings)
            if mode == "pair":
                score = FaceMatcher.similarity(
                    references[0]["embedding"], references[1]["embedding"]
                )
                return {
                    "mode": "pair",
                    "matched": score >= threshold,
                    "similarity": round(score, 3),
                    "threshold": threshold,
                    "target_box": references[1]["box"],
                    "note": "Possible same-person match, not identity proof. Comparison images were not saved.",
                }
            matches = []
            with connect() as db:
                rows = db.execute(
                    "SELECT * FROM photos ORDER BY filename, id"
                ).fetchall()
            for row in rows:
                cached = json.loads(row["faces"]) if row["faces"] else None
                if not isinstance(cached, dict) or cached.get("version") != 2:
                    image = load_image(data / "originals" / row["original"], 2048)
                    faces = matcher.encode(image)
                    with connect() as db:
                        db.execute(
                            "UPDATE photos SET faces=? WHERE id=?",
                            (json.dumps({"version": 2, "faces": faces}), row["id"]),
                        )
                else:
                    faces = cached["faces"]
                boxes = match_faces(references, faces, threshold, team)
                if boxes:
                    matches.append(
                        public(row)
                        | {
                            "similarity": max(b["similarity"] for b in boxes),
                            "matched_faces": boxes,
                        }
                    )
            return {
                "photos": sorted(matches, key=lambda p: -p["similarity"]),
                "references": len(references),
                "note": "Possible matches. Dotted boxes mark candidate faces; ambiguity is flagged. References were not saved.",
            }
        finally:
            face_lock.release()

    @app.get("/api/agent")
    def agent_status():
        return {"job": job.copy(), "result": agent_result.copy()}

    @app.post("/api/agent")
    def start_agent(options: AgentRequest):
        try:
            planner = PhotoAgent(options.model)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

        def run_agent():
            deadline = time.monotonic() + options.max_minutes * 60
            tool_tokens = 0

            def check():
                if cancel.is_set() or time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Agent stopped between calls. Previous picks and results remain available."
                    )

            def rows():
                with connect() as db:
                    return db.execute(
                        "SELECT * FROM photos ORDER BY filename,id"
                    ).fetchall()

            def inspect_event():
                records = rows()
                return {
                    "count": len(records),
                    "picked": sum(r["picked"] for r in records),
                    "summary": "Event inspected locally.",
                }

            def get_shortlist():
                return {
                    "photos": [public(r) for r in rows() if r["picked"]],
                    "summary": "Existing AI shortlist; no files changed.",
                }

            def visual_search(query):
                nonlocal tool_tokens
                records = rows()
                found = []
                job.update(total=len(records), reviewed=0)
                for index, row in enumerate(records):
                    check()
                    decision, used, hits = visual_assessment(
                        (data / "previews" / f"{row['id']}.jpg").read_bytes(),
                        row["id"],
                        query,
                        options.model,
                        data / "cache" / "visual",
                    )
                    tool_tokens += used
                    job.update(
                        reviewed=index + 1,
                        tokens=tool_tokens,
                        cache_hits=job["cache_hits"] + hits,
                    )
                    if decision["match"]:
                        found.append(
                            public(row) | {"search_reason": decision["reason"]}
                        )
                return {
                    "photos": found,
                    "summary": f"Visually checked {len(records)} photos; {len(found)} possible matches. Small logos may be missed.",
                }

            def count_faces(min_faces, max_faces=1000):
                if not face_lock.acquire(blocking=False):
                    raise RuntimeError("A face job is already running.")
                try:
                    detector = FaceMatcher(Path.cwd() / ".cache/models")
                    found = []
                    records = rows()
                    job.update(total=len(records), reviewed=0)
                    for index, row in enumerate(records):
                        check()
                        faces = detector.detect(
                            load_image(data / "originals" / row["original"], 2048)
                        )
                        if min_faces <= len(faces) <= max_faces:
                            found.append(
                                public(row)
                                | {
                                    "face_count": len(faces),
                                    "detected_faces": [
                                        {"box": f["box"]} for f in faces
                                    ],
                                }
                            )
                        job["reviewed"] = index + 1
                    return {
                        "photos": found,
                        "summary": f"Counted detectable faces in {len(records)} photos. Small/occluded faces can be missed; no identity embeddings stored.",
                    }
                finally:
                    face_lock.release()

            def progress(event):
                job.update(phase=event["phase"], agent_step=event["step"])
                if "tool" in event:
                    job["current_tool"] = event["tool"]
                if "trace" in event:
                    job["trace"] = event["trace"]

            try:
                result = planner.run(
                    options.query,
                    {
                        "inspect_event": inspect_event,
                        "get_shortlist": get_shortlist,
                        "visual_search": visual_search,
                        "count_faces": count_faces,
                    },
                    check=check,
                    progress=progress,
                )
                result["tokens"] += tool_tokens
                result["query"] = options.query
                agent_result.clear()
                agent_result.update(result)
                job.update(
                    tokens=result["tokens"],
                    phase=f"Agent complete: {len(result['photos'])} photo results",
                )
            except Exception as exc:
                job.update(
                    error=(
                        str(exc)
                        if isinstance(exc, (ValueError, RuntimeError))
                        else "Agent failed; previous results remain available."
                    ),
                    phase="Agent stopped",
                )
            finally:
                job["running"] = False

        with lock:
            if job["running"]:
                raise HTTPException(409, "A job is already running.")
            cancel.clear()
            job.update(
                running=True,
                kind="agent",
                phase="Planning",
                total=0,
                reviewed=0,
                error="",
                tokens=0,
                cache_hits=0,
                agent_step=0,
                trace=[],
                current_tool="",
            )
            threading.Thread(target=run_agent, daemon=True).start()
        return {"started": True}

    @app.delete("/api/face-index")
    def clear_face_index():
        with face_lock, connect() as db:
            db.execute("UPDATE photos SET faces=NULL")
        return {"cleared": True}

    return app

"""Local web app: sign in, confirm lab rows, and read them as meters."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

import hmac
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import (
    hash_password,
    normalize_email,
    valid_email,
    valid_password,
    verify_password,
)
from app.corpus import VISITS
from app.db import (
    create_user,
    get_llm_settings,
    get_report,
    get_summary,
    init_db,
    insert_report,
    list_reports,
    results_for_report,
    results_for_user,
    save_llm_settings,
    save_summary,
    user_by_email,
    user_by_id,
)
from app.extract import ParseError, extract_pdf, make_row, pdf_text, text_is_unsafe
from app.facts import (
    PROMPT_RULES,
    PromptUnsafe,
    changes_for,
    fact_hash,
    fact_payload,
    meters_for,
    summary_is_grounded,
    summary_is_prose,
)
from app.llm import (
    LOCAL_MODELS,
    OPENAI_MODELS,
    LlmError,
    chat_complete,
    config_from_row,
    parse_settings_form,
    rows_from_report_text,
)
from app.paths import DATA, FIXTURES, ROOT, STATIC, TEMPLATES
from app.pdfgen import write_fixtures

MAX_PDF_BYTES = 5_000_000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PUBLIC_PATHS = {"/login", "/register"}


@dataclass(frozen=True)
class Settings:
    db_path: Path
    secret: str
    fixture_dir: Path
    data_dir: Path


def _load_secret(data_dir: Path) -> str:
    from_env = os.environ.get("SESSION_SECRET", "").strip()
    if from_env:
        return from_env
    path = data_dir / "session.secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    path.write_text(secret, encoding="utf-8")
    os.chmod(path, 0o600)
    return secret


def default_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    data_dir = DATA
    db_value = os.environ.get("LAB_DB_PATH", "").strip()
    db_path = Path(db_value) if db_value else data_dir / "labs.sqlite"
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    return Settings(
        db_path=db_path,
        secret=_load_secret(data_dir),
        fixture_dir=FIXTURES,
        data_dir=data_dir,
    )


def _tokens_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or default_settings()
    init_db(config.db_path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Personal lab tracker")
    templates = Jinja2Templates(directory=str(TEMPLATES))
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    def render(request: Request, name: str, status: int = 200, **context):
        user = None
        user_id = request.session.get("user_id")
        if user_id:
            user = user_by_id(config.db_path, int(user_id))
        context.update(
            {
                "csrf": _ensure_csrf(request),
                "flash": request.session.pop("flash", None),
                "user": user,
            }
        )
        return templates.TemplateResponse(
            request=request,
            name=name,
            context=context,
            status_code=status,
        )

    def flash(request: Request, message: str) -> None:
        request.session["flash"] = message

    @app.middleware("http")
    async def require_sign_in(request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path in PUBLIC_PATHS:
            return await call_next(request)
        if not request.session.get("user_id"):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    def signed_in_user(request: Request) -> dict | None:
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        return user_by_id(config.db_path, int(user_id))

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        user = signed_in_user(request)
        if user is None:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        stored = results_for_user(config.db_path, user["id"])
        prompt_error = ""
        payload = ""
        if stored:
            try:
                payload = fact_payload(stored)
            except PromptUnsafe as exc:
                prompt_error = str(exc)
        llm = config_from_row(get_llm_settings(config.db_path, user["id"]))
        saved = get_summary(config.db_path, user["id"]) if payload else None
        summary = None
        if saved and summary_is_prose(saved["body"]):
            summary = {
                "body": saved["body"],
                "model_label": saved["model_label"],
                "stale": saved["fact_hash"] != fact_hash(payload),
            }
        meters = meters_for(stored)
        return render(
            request,
            "dashboard.html",
            reports=list_reports(config.db_path, user["id"]),
            meters=meters,
            outside_count=sum(1 for item in meters if item.flag in {"above", "below"}),
            changes=changes_for(stored),
            history=sorted(stored, key=lambda item: item.collected_on, reverse=True),
            prompt_error=prompt_error,
            has_results=bool(stored),
            summary=summary,
            summary_ready=bool(llm.summary_model),
            summary_provider=llm.summary_provider,
            summary_model=llm.summary_model,
            key_saved=llm.key_saved,
            extraction_model=llm.extraction_model,
            extraction_provider=llm.extraction_provider,
        )

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/", status_code=303)
        return render(request, "login.html")

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            return render(request, "login.html", status=400, error="The form expired. Try again.")
        email = normalize_email(str(form.get("email", "")))
        password = str(form.get("password", ""))
        user = user_by_email(config.db_path, email)
        if user is None or not verify_password(password, user["password_hash"]):
            return render(
                request,
                "login.html",
                status=401,
                error="Email or password does not match an account on this machine.",
                email=email,
            )
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)

    @app.get("/register", response_class=HTMLResponse)
    def register_form(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/", status_code=303)
        return render(request, "register.html")

    @app.post("/register")
    async def register_submit(request: Request):
        form = await request.form()
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            return render(
                request, "register.html", status=400, error="The form expired. Try again."
            )
        email = normalize_email(str(form.get("email", "")))
        password = str(form.get("password", ""))
        if not valid_email(email):
            return render(
                request,
                "register.html",
                status=400,
                error="Enter an email address to use as the account name.",
                email=email,
            )
        if not valid_password(password):
            return render(
                request,
                "register.html",
                status=400,
                error="Use a password of at least 8 characters.",
                email=email,
            )
        if user_by_email(config.db_path, email):
            return render(
                request,
                "register.html",
                status=400,
                error="An account with that email already exists on this machine.",
                email=email,
            )
        user_id = create_user(config.db_path, email, hash_password(password))
        request.session["user_id"] = user_id
        flash(request, "Account created on this machine. The dashboard starts empty.")
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    async def logout(request: Request):
        form = await request.form()
        if _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_form(request: Request):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        llm = config_from_row(get_llm_settings(config.db_path, user["id"]))
        return render(
            request,
            "settings.html",
            llm=llm,
            local_models=LOCAL_MODELS,
            openai_models=OPENAI_MODELS,
        )

    @app.post("/settings")
    async def settings_save(request: Request):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        existing = config_from_row(get_llm_settings(config.db_path, user["id"]))
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            return render(
                request,
                "settings.html",
                status=400,
                error="The form expired. Try again.",
                llm=existing,
                local_models=LOCAL_MODELS,
                openai_models=OPENAI_MODELS,
            )
        parsed, error = parse_settings_form(form, existing)
        if parsed is None:
            return render(
                request,
                "settings.html",
                status=400,
                error=error,
                llm=existing,
                local_models=LOCAL_MODELS,
                openai_models=OPENAI_MODELS,
            )
        save_llm_settings(
            config.db_path,
            user["id"],
            {
                "local_base_url": parsed.local_base_url,
                "openai_api_key": parsed.openai_api_key,
                "extraction_provider": parsed.extraction_provider,
                "extraction_model": parsed.extraction_model,
                "summary_provider": parsed.summary_provider,
                "summary_model": parsed.summary_model,
            },
        )
        flash(request, "Model settings saved on this machine.")
        return RedirectResponse("/settings", status_code=303)

    @app.post("/summary")
    async def generate_summary(request: Request):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            flash(request, "The form expired. Try Generate summary again.")
            return RedirectResponse("/", status_code=303)
        stored = results_for_user(config.db_path, user["id"])
        if not stored:
            flash(request, "Save a report before generating a summary.")
            return RedirectResponse("/", status_code=303)
        try:
            payload = fact_payload(stored)
        except PromptUnsafe as exc:
            flash(request, str(exc))
            return RedirectResponse("/", status_code=303)
        llm = config_from_row(get_llm_settings(config.db_path, user["id"]))
        try:
            with _llm_client(request) as client:
                reply = chat_complete(llm, "summary", PROMPT_RULES, payload, client)
        except LlmError as exc:
            flash(request, str(exc))
            return RedirectResponse("/", status_code=303)
        if not summary_is_prose(reply):
            flash(
                request,
                "The summary was discarded because the model returned the fact sheet instead of a paragraph.",
            )
            return RedirectResponse("/", status_code=303)
        if not summary_is_grounded(reply, payload):
            flash(
                request,
                "The summary was discarded because it added a number or an identifier that is not on the fact sheet.",
            )
            return RedirectResponse("/", status_code=303)
        _provider, model = llm.task("summary")
        save_summary(
            config.db_path,
            user["id"],
            fact_hash(payload),
            f"{llm.summary_provider}:{model}",
            reply.strip(),
        )
        flash(request, "Summary written from the fact sheet.")
        return RedirectResponse("/", status_code=303)

    @app.get("/reports/{report_id}", response_class=HTMLResponse)
    def report_detail(request: Request, report_id: int):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        report = get_report(config.db_path, user["id"], report_id)
        if report is None:
            return render(
                request,
                "missing.html",
                status=404,
                message="That report is not in this account.",
            )
        return render(
            request,
            "report.html",
            report=report,
            rows=results_for_report(config.db_path, user["id"], report_id),
        )

    @app.post("/upload")
    async def upload(request: Request):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            flash(request, "The form expired. Try the upload again.")
            return RedirectResponse("/", status_code=303)
        upload_file = form.get("report")
        if upload_file is None or not getattr(upload_file, "filename", ""):
            flash(request, "Choose a PDF lab report to upload.")
            return RedirectResponse("/", status_code=303)
        filename = Path(str(upload_file.filename)).name
        if not filename.lower().endswith(".pdf"):
            flash(request, "Upload a digital PDF. Scanned photos are not read yet.")
            return RedirectResponse("/", status_code=303)
        payload = await upload_file.read()
        if len(payload) > MAX_PDF_BYTES:
            flash(request, "That PDF is larger than 5 MB.")
            return RedirectResponse("/", status_code=303)
        if not payload.startswith(b"%PDF"):
            flash(request, "That file is not a PDF.")
            return RedirectResponse("/", status_code=303)
        pending_dir = config.data_dir / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending_path = pending_dir / f"{uuid.uuid4().hex}.pdf"
        pending_path.write_bytes(payload)
        try:
            extraction = _read_upload(request, config.db_path, user["id"], pending_path)
        except (ParseError, LlmError) as exc:
            pending_path.unlink(missing_ok=True)
            flash(request, str(exc))
            return RedirectResponse("/", status_code=303)
        request.session["pending"] = _pending_session(filename, pending_path, extraction)
        return RedirectResponse("/review", status_code=303)

    @app.get("/review", response_class=HTMLResponse)
    def review_form(request: Request):
        pending = request.session.get("pending")
        if not pending:
            flash(request, "Upload a PDF to review its rows before saving.")
            return RedirectResponse("/", status_code=303)
        return render(request, "review.html", pending=pending)

    @app.post("/review")
    async def review_save(request: Request):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            flash(request, "The form expired. Review the rows again.")
            return RedirectResponse("/review", status_code=303)
        pending = request.session.get("pending")
        if not pending:
            flash(request, "Upload a PDF to review its rows before saving.")
            return RedirectResponse("/", status_code=303)
        collected_on = str(form.get("collected_on", "")).strip()
        panel_name = str(form.get("panel_name", "")).strip() or "Lab panel"
        if not DATE_RE.fullmatch(collected_on):
            flash(request, "Collection date must be YYYY-MM-DD.")
            return RedirectResponse("/review", status_code=303)
        indexes = sorted(
            {
                int(key.rsplit("_", 1)[1])
                for key in form.keys()
                if key.startswith("display_name_") and key.rsplit("_", 1)[1].isdigit()
            }
        )
        rows = []
        for index in indexes:
            display_name = str(form.get(f"display_name_{index}", "")).strip()
            value_text = str(form.get(f"value_text_{index}", "")).strip()
            unit = str(form.get(f"unit_{index}", "")).strip()
            ref_text = str(form.get(f"ref_text_{index}", "")).strip()
            if not display_name and not value_text:
                continue
            if not display_name or not value_text:
                flash(request, "Each row needs a test name and a value.")
                return RedirectResponse("/review", status_code=303)
            blob = " ".join((display_name, value_text, unit, ref_text))
            if text_is_unsafe(blob):
                flash(
                    request,
                    "A row still looks like a name, email, phone, or record id. Keep only the test and its value.",
                )
                return RedirectResponse("/review", status_code=303)
            rows.append(make_row(display_name, value_text, unit, ref_text))
        if not rows:
            flash(request, "Keep at least one result row.")
            return RedirectResponse("/review", status_code=303)
        pending_path = _pending_file(config.data_dir, str(pending.get("pending_path", "")))
        if pending_path is None or not pending_path.exists():
            request.session.pop("pending", None)
            flash(request, "The uploaded PDF expired. Upload it again.")
            return RedirectResponse("/", status_code=303)
        stored_dir = config.data_dir / "uploads" / str(user["id"])
        stored_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}.pdf"
        stored_file = stored_dir / stored_name
        shutil.move(str(pending_path), stored_file)
        relative = stored_file.relative_to(config.data_dir).as_posix()
        try:
            report_id = insert_report(
                config.db_path,
                user["id"],
                collected_on,
                panel_name,
                str(pending.get("source_name") or "report.pdf"),
                relative,
                rows,
            )
        except sqlite3.IntegrityError:
            stored_file.unlink(missing_ok=True)
            flash(request, "That report is already saved in this account.")
            request.session.pop("pending", None)
            return RedirectResponse("/", status_code=303)
        request.session.pop("pending", None)
        flash(request, "Report saved on this machine.")
        return RedirectResponse(f"/reports/{report_id}", status_code=303)

    @app.post("/demo")
    async def load_demo(request: Request):
        user = signed_in_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        if not _tokens_match(str(form.get("csrf", "")), request.session.get("csrf", "")):
            flash(request, "The form expired. Try Load demo record again.")
            return RedirectResponse("/", status_code=303)
        if not any((config.fixture_dir / visit["file"]).exists() for visit in VISITS):
            write_fixtures(config.fixture_dir)
        loaded = 0
        skipped = 0
        for visit in VISITS:
            source = config.fixture_dir / visit["file"]
            extraction = extract_pdf(source)
            stored_dir = config.data_dir / "uploads" / str(user["id"])
            stored_dir.mkdir(parents=True, exist_ok=True)
            stored_file = stored_dir / f"{uuid.uuid4().hex}.pdf"
            shutil.copy(source, stored_file)
            relative = stored_file.relative_to(config.data_dir).as_posix()
            try:
                insert_report(
                    config.db_path,
                    user["id"],
                    extraction.collected_on,
                    extraction.panel_name,
                    visit["file"],
                    relative,
                    list(extraction.rows),
                )
                loaded += 1
            except sqlite3.IntegrityError:
                stored_file.unlink(missing_ok=True)
                skipped += 1
        if loaded:
            flash(request, f"Loaded {loaded} fictional visit{'s' if loaded != 1 else ''} into this account.")
        elif skipped:
            flash(request, "Those demo visits are already in this account.")
        return RedirectResponse("/", status_code=303)

    app.add_middleware(_session_middleware_class(), secret_key=config.secret)
    return app


def _llm_client(request: Request) -> httpx.Client:
    factory = getattr(request.app.state, "llm_client_factory", None)
    if factory is not None:
        return factory()
    return httpx.Client(timeout=60.0)


def _pending_session(filename: str, pending_path: Path, extraction) -> dict:
    return {
        "source_name": filename,
        "pending_path": str(pending_path),
        "collected_on": extraction.collected_on,
        "panel_name": extraction.panel_name,
        "removed": list(extraction.removed),
        "sent_provider": extraction.sent_provider,
        "rows": [
            {
                "display_name": row.display_name,
                "value_text": row.value_text,
                "unit": row.unit,
                "ref_text": row.ref_text,
                "flag": row.flag,
            }
            for row in extraction.rows
        ],
    }


def _read_upload(request: Request, db_path: Path, user_id: int, pending_path: Path):
    report_text = pdf_text(pending_path)
    llm = config_from_row(get_llm_settings(db_path, user_id))
    if llm.extraction_model:
        with _llm_client(request) as client:
            return rows_from_report_text(report_text, llm, client)
    try:
        return extract_pdf(pending_path)
    except ParseError as exc:
        raise ParseError(
            str(exc) + " Choose an extraction model in Settings to read this PDF with a model."
        ) from exc


def _pending_file(data_dir: Path, raw: str) -> Path | None:
    if not raw:
        return None
    pending_root = (data_dir / "pending").resolve()
    candidate = Path(raw).resolve()
    if not candidate.is_relative_to(pending_root):
        return None
    return candidate


def _session_middleware_class():
    from starlette.middleware.sessions import SessionMiddleware

    return SessionMiddleware


app = create_app()

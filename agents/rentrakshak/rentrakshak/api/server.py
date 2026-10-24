"""FastAPI server: REST API + static HTML demo frontend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rentrakshak.db.database import init_db
from rentrakshak.models.schemas import AnonymousExperienceInput, VacatingPostInput
from rentrakshak.services.ask_helper import answer_question
from rentrakshak.services.checklist import build_rental_checklist, get_karnataka_rental_guidance
from rentrakshak.services.community import create_anonymous_experience, search_anonymous_experiences
from rentrakshak.services.demo_seed import seed_demo
from rentrakshak.services.locality_summary import POPULAR_LOCALITIES, popular_locality_cards
from rentrakshak.services.rent_estimator import estimate_bengaluru_rent
from rentrakshak.services.listing_upload import ListingUploadError, process_listing_upload
from rentrakshak.services.safety_report import generate_rental_safety_report
from rentrakshak.services.vacating import create_vacating_post, search_available_rooms

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"

app = FastAPI(title="RentRakshak API", version="0.2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SafetyReportRequest(BaseModel):
    listing_text: str = Field(..., min_length=10)
    chat_text: str | None = None
    locality_hint: str | None = None
    monthly_rent_inr: int | None = None
    deposit_inr: int | None = None
    bhk: str | None = None
    furnishing: str | None = None
    property_type: str | None = None


class ExperienceCreateRequest(BaseModel):
    locality: str
    property_type: str
    category: str
    sentiment: str
    experience_text: str = Field(..., min_length=20)
    rent_band: str | None = None
    move_period: str | None = None
    rating_maintenance: int | None = Field(None, ge=1, le=5)
    rating_communication: int | None = Field(None, ge=1, le=5)


class VacatingCreateRequest(BaseModel):
    locality: str
    property_type: str = "apartment"
    room_type: str = "private room"
    monthly_rent_inr: int = Field(..., gt=0)
    deposit_inr: int | None = None
    availability_date: str
    post_kind: str = "room_takeover"
    description: str = Field(..., min_length=15)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rentrakshak", "version": "0.2.1"}


@app.get("/api/localities")
def api_localities() -> dict[str, Any]:
    return {
        "popular": popular_locality_cards(),
        "all_supported": POPULAR_LOCALITIES,
        "disclaimer": "Demo comparables — not live market prices.",
    }


@app.get("/api/rent-estimate")
def api_rent_estimate(
    locality: str,
    bhk: str | None = None,
    furnishing: str | None = None,
    property_type: str | None = None,
) -> dict[str, Any]:
    result = estimate_bengaluru_rent(locality, bhk=bhk, furnishing=furnishing, property_type=property_type)
    return result.model_dump()


@app.post("/api/safety-report")
def api_safety_report(body: SafetyReportRequest) -> dict[str, Any]:
    report = generate_rental_safety_report(
        body.listing_text,
        body.chat_text,
        locality_hint=body.locality_hint,
        monthly_rent_inr=body.monthly_rent_inr,
        deposit_inr=body.deposit_inr,
        bhk=body.bhk,
        furnishing=body.furnishing,
        property_type=body.property_type,
    )
    return report.model_dump()


@app.post("/api/upload-listing")
async def api_upload_listing(file: UploadFile = File(...)) -> dict[str, Any]:
    name = file.filename or "upload"
    raw = await file.read()
    try:
        return process_listing_upload(raw, name)
    except ListingUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/demo/seed")
def api_seed_demo() -> dict[str, str]:
    path = seed_demo()
    return {"message": "Demo data loaded (12 experiences, 4 vacating posts)", "db_path": str(path)}


@app.get("/api/experiences")
def api_experiences(
    locality: str | None = None,
    sentiment: str | None = None,
    category: str | None = None,
    property_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    return search_anonymous_experiences(
        locality=locality,
        sentiment=sentiment or None,
        category=category or None,
        property_type=property_type or None,
        limit=min(limit, 50),
    )


@app.post("/api/experiences")
def api_create_experience(body: ExperienceCreateRequest) -> dict[str, Any]:
    try:
        data = AnonymousExperienceInput(
            locality=body.locality,
            property_type=body.property_type,
            category=body.category,
            sentiment=body.sentiment,
            experience_text=body.experience_text,
            rent_band=body.rent_band,
            move_period=body.move_period,
            rating_maintenance=body.rating_maintenance,
            rating_communication=body.rating_communication,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return create_anonymous_experience(data)


@app.get("/api/vacating")
def api_vacating(locality: str | None = None, max_rent_inr: int | None = None) -> dict[str, Any]:
    return search_available_rooms(locality=locality, max_rent_inr=max_rent_inr)


@app.post("/api/vacating")
def api_create_vacating(body: VacatingCreateRequest) -> dict[str, Any]:
    from datetime import date as date_cls

    try:
        ad = date_cls.fromisoformat(body.availability_date)
        data = VacatingPostInput(
            locality=body.locality,
            property_type=body.property_type,
            room_type=body.room_type,
            monthly_rent_inr=body.monthly_rent_inr,
            deposit_inr=body.deposit_inr,
            availability_date=ad,
            post_kind=body.post_kind,
            description=body.description,
            contact_method="web-demo-poster",
            owner_permission_ack=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = create_vacating_post(data, publish=True)
    if not out.get("success"):
        raise HTTPException(status_code=400, detail=out.get("message", "Failed"))
    return out


@app.get("/api/checklist")
def api_checklist() -> dict[str, Any]:
    items = build_rental_checklist()
    legal = get_karnataka_rental_guidance()
    return {
        "items": [i.model_dump() for i in items],
        "legal_sources": [r.model_dump() for r in legal],
    }


@app.post("/api/ask")
def api_ask(body: AskRequest) -> dict[str, str]:
    return answer_question(body.question)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


if WEB_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")

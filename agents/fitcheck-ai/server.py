"""FitCheck AI web server — streams the council's debate to the browser.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import base64
import json
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from fitcheck_ai import color_engine as ce  # noqa: E402
from fitcheck_ai.agent import MODEL_ID, VISION_MODEL_ID, root_agent  # noqa: E402
from fitcheck_ai.models import api_key, is_hosted, provider_label  # noqa: E402
from fitcheck_ai.wardrobe import load_wardrobe  # noqa: E402

APP_NAME = "fitcheck_ai"
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="FitCheck AI")
session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)

AGENT_LABELS = {
    "ColorLab": "Color Lab", "OutfitReader": "Outfit Reader", "Stylist": "Stylist",
    "ColorExpert": "Color Expert", "OccasionExpert": "Occasion Expert",
    "ColorAnalyst": "Color Analyst", "ShoppingSkeptic": "Shopping Skeptic",
    "HeadStylist": "Head Stylist",
}


class FitCheckRequest(BaseModel):
    outfit_photo: str | None = None          # data URL
    selfie: str | None = None                # data URL
    liked_colors: list[str] = Field(default_factory=list)
    selected_item_ids: list[str] = Field(default_factory=list)
    occasion: str = ""
    notes: str = ""


def _split_data_url(data_url: str) -> tuple[bytes, str]:
    if data_url.startswith("data:"):
        header, b64 = data_url.split(",", 1)
        mime = header[5:].split(";")[0] or "image/jpeg"
    else:
        b64, mime = data_url, "image/jpeg"
    return base64.b64decode(b64), mime


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    blob = text[start:end + 1]
    for candidate in (blob, re.sub(r",\s*([}\]])", r"\1", blob)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _score_from(text: str | None) -> float | None:
    m = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9])?)\s*/\s*10", text or "", re.I)
    return float(m.group(1)) if m else None


def build_result(state: dict) -> dict:
    lab = state.get("color_lab", {})
    card = _parse_json(state.get("scorecard_raw", "")) or {}

    takes = {k: state.get(k) for k in
             ("stylist_take", "color_take", "occasion_take", "analyst_take", "skeptic_take")}
    fallback = {"silhouette": _score_from(takes["stylist_take"]),
                "color": _score_from(takes["color_take"]),
                "occasion": _score_from(takes["occasion_take"]),
                "palette_fit": _score_from(takes["analyst_take"])}
    scores = {k: (card.get("scores") or {}).get(k) or v for k, v in fallback.items()}
    nums = [float(v) for v in scores.values() if isinstance(v, (int, float))]
    overall = card.get("overall_score") or (round(sum(nums) / len(nums), 1) if nums else None)

    combos = {c["id"]: c for c in lab.get("combos", [])}
    alts = []
    for a in card.get("alternatives") or []:
        cid = str(a.get("combo_id", "")).strip().upper()
        if cid in combos:
            alts.append({"combo_id": cid, "why": a.get("why", ""), "items": combos[cid]["items"],
                         "scheme": combos[cid]["harmony"]["scheme"]})
    if not alts:  # model didn't return usable IDs → fall back to top deterministic combos
        alts = [{"combo_id": c["id"], "why": f"{c['harmony']['scheme']} · fits your palette",
                 "items": c["items"], "scheme": c["harmony"]["scheme"]}
                for c in list(combos.values())[:3]]

    return {
        "verdict": card.get("verdict") or "The council has spoken — see the details below.",
        "overall_score": overall,
        "scores": scores,
        "debate": card.get("debate") or [],
        "improvements": card.get("improvements") or [],
        "alternatives": alts,
        "color_board": card.get("color_board") or {},
        "buy_next": card.get("buy_next") or "",
        "takes": takes,
        "outfit_notes": state.get("outfit_notes"),
        "palette": lab.get("palette"),
        "selfie": lab.get("selfie"),
        "outfit_photo": lab.get("outfit_photo"),
        "harmony": lab.get("harmony"),
        "model": MODEL_ID,
        "parsed_ok": bool(card),
    }


def explain_error(exc: Exception) -> str:
    """Turn API failures into a fix the user can act on. Only real Gemini API
    errors (with an HTTP status) get API-specific advice."""
    from google.genai import errors as genai_errors

    msg = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, genai_errors.APIError):
        code, low = exc.code, msg.lower()
        if code in (401, 403) or "api key" in low or "api_key" in low:
            return ("Gemini API rejected your key — check GOOGLE_API_KEY in .env "
                    "(create one at https://aistudio.google.com/apikey). " + msg[:300])
        if code == 429:
            return ("Gemini API quota hit even after retries — wait a minute and try again, "
                    "or set FITCHECK_THINKING=minimal to use fewer tokens. " + msg[:300])
        if code == 404:
            return (f"Model '{MODEL_ID}' isn't available to your key. Run "
                    "`python scripts/check_api.py` to list Gemma models you can use. " + msg[:300])
        if code >= 500:
            return "Gemini API is having trouble right now (server error) — try again shortly. " + msg[:300]
        return "Gemini API error: " + msg[:400]
    if "ollama" in MODEL_ID and "connect" in msg.lower():
        return msg + " — is Ollama running? Try `ollama serve` and `ollama pull gemma3:4b`."
    return msg


@app.get("/api/health")
def health():
    """What the UI needs to show which Gemma is running — never exposes the key."""
    return {
        "model": MODEL_ID, "vision_model": VISION_MODEL_ID,
        "provider": provider_label(MODEL_ID),
        "api_key_configured": bool(api_key()) if is_hosted(MODEL_ID) else None,
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/wardrobe")
def wardrobe():
    return load_wardrobe()


@app.post("/api/colorlab")
def colorlab(req: FitCheckRequest):
    """Instant, LLM-free colour board preview (selfie + favourite colours)."""
    selfie = ce.analyze_selfie(req.selfie) if req.selfie else None
    skin = ce.SkinReport(**selfie["skin"]) if selfie else None
    return {"selfie": selfie, "palette": ce.build_palette(skin, req.liked_colors)}


@app.post("/api/fitcheck")
async def fitcheck(req: FitCheckRequest):
    user_id, session_id = "local-user", str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id,
        state={
            "outfit_photo_b64": req.outfit_photo, "selfie_b64": req.selfie,
            "liked_colors": req.liked_colors, "selected_item_ids": req.selected_item_ids,
            "occasion": req.occasion, "notes": req.notes,
        },
    )
    parts = [types.Part(text=f"Please check my outfit for: {req.occasion or 'an everyday outing'}.")]
    if req.outfit_photo:
        data, mime = _split_data_url(req.outfit_photo)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    message = types.Content(role="user", parts=parts)

    async def stream():
        try:
            async for event in runner.run_async(user_id=user_id, session_id=session_id,
                                                new_message=message):
                # skip Gemma 4 "thinking" parts — only show each expert's final answer
                text = "".join(p.text or "" for p in (event.content.parts if event.content else [])
                               if not getattr(p, "thought", False))
                if text.strip() and event.author in AGENT_LABELS:
                    yield json.dumps({"type": "agent", "agent": event.author,
                                      "label": AGENT_LABELS[event.author], "text": text}) + "\n"
            session = await session_service.get_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id)
            yield json.dumps({"type": "result", "result": build_result(session.state)}) + "\n"
        except Exception as exc:  # surface model/runtime errors to the UI
            yield json.dumps({"type": "error", "message": explain_error(exc)}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


app.mount("/static", StaticFiles(directory=STATIC), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))

"""FitCheck AI web server. Streams each agent's verdict to the browser as it arrives.

    uvicorn main:app --reload
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
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import colors  # noqa: E402
from council import MODEL, root_agent  # noqa: E402
from wardrobe import load_wardrobe  # noqa: E402

APP_NAME = "fitcheck"
INDEX_HTML = Path(__file__).parent / "static" / "index.html"
AGENTS = {"ColorLab", "OutfitReader", "Stylist", "ColorExpert", "OccasionExpert",
          "ColorAnalyst", "ShoppingSkeptic", "HeadStylist"}

app = FastAPI(title="FitCheck AI")
sessions = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=sessions)


class FitCheckRequest(BaseModel):
    outfit_photo: str | None = None  # data URL
    selfie: str | None = None  # data URL
    liked_colors: list[str] = Field(default_factory=list)
    selected_item_ids: list[str] = Field(default_factory=list)
    occasion: str = ""
    notes: str = ""


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    header, _, payload = data_url.partition(",")
    mime = header[5:].split(";")[0] if header.startswith("data:") else "image/jpeg"
    return base64.b64decode(payload or header), mime or "image/jpeg"


def parse_json(text: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating fences and trailing commas."""
    text = re.sub(r"```(?:json)?", "", text or "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    blob = text[start:end + 1]
    for candidate in (blob, re.sub(r",\s*([}\]])", r"\1", blob)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return {}


def score_from(text: str | None) -> float | None:
    match = re.search(r"SCORE:\s*(\d+(?:\.\d)?)\s*/\s*10", text or "", re.I)
    return float(match.group(1)) if match else None


def build_result(state: dict) -> dict:
    lab = state.get("color_lab", {})
    card = parse_json(state.get("scorecard_raw", ""))

    # Fall back to each expert's own SCORE line if the scorecard is missing a value.
    expert_scores = {
        "silhouette": score_from(state.get("stylist_take")),
        "color": score_from(state.get("color_take")),
        "occasion": score_from(state.get("occasion_take")),
        "palette_fit": score_from(state.get("analyst_take")),
    }
    scores = {k: (card.get("scores") or {}).get(k) or v for k, v in expert_scores.items()}
    numbers = [float(v) for v in scores.values() if isinstance(v, (int, float))]
    overall = card.get("overall_score") or (round(sum(numbers) / len(numbers), 1) if numbers else None)

    # Only keep alternatives that point at real combos; otherwise show the top ones.
    combos = {c["id"]: c for c in lab.get("combos", [])}
    alternatives = [
        {"combo_id": cid, "why": alt.get("why", ""), "items": combos[cid]["items"],
         "scheme": combos[cid]["harmony"]["scheme"]}
        for alt in card.get("alternatives") or []
        if (cid := str(alt.get("combo_id", "")).strip().upper()) in combos
    ] or [
        {"combo_id": c["id"], "why": "Fits your palette", "items": c["items"],
         "scheme": c["harmony"]["scheme"]}
        for c in list(combos.values())[:3]
    ]

    return {
        "verdict": card.get("verdict") or "Here's what the council thinks.",
        "overall_score": overall,
        "scores": scores,
        "debate": card.get("debate") or [],
        "improvements": card.get("improvements") or [],
        "alternatives": alternatives,
        "color_board": card.get("color_board") or {},
        "buy_next": card.get("buy_next") or "",
        "palette": lab.get("palette"),
        "selfie": lab.get("selfie"),
        "outfit_photo": lab.get("outfit_photo"),
        "model": MODEL,
        "parsed_ok": bool(card),
    }


def error_message(exc: Exception) -> str:
    if isinstance(exc, genai_errors.APIError):
        if exc.code in (400, 401, 403) and "key" in str(exc).lower():
            return "The Gemini API rejected your key. Check GOOGLE_API_KEY in .env."
        if exc.code == 429:
            return "Gemini API rate limit reached. Wait a minute and try again."
        if exc.code == 404:
            return f"Model {MODEL} isn't available for your API key."
        if exc.code >= 500:
            return "The Gemini API is having problems right now. Try again shortly."
    return f"{type(exc).__name__}: {exc}"


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)


@app.get("/api/health")
def health():
    return {"model": MODEL, "api_key_set": bool(os.getenv("GOOGLE_API_KEY"))}


@app.get("/api/wardrobe")
def wardrobe():
    return load_wardrobe()


@app.post("/api/palette")
def palette(req: FitCheckRequest):
    """Quick colour board from a selfie and favourite colours, without calling the model."""
    selfie = colors.analyze_selfie(req.selfie) if req.selfie else None
    skin = colors.SkinReport(**selfie["skin"]) if selfie else None
    return {"selfie": selfie, "palette": colors.build_palette(skin, req.liked_colors)}


@app.post("/api/fitcheck")
async def fitcheck(req: FitCheckRequest):
    user_id, session_id = "local", str(uuid.uuid4())
    await sessions.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id,
        state={
            "outfit_photo_b64": req.outfit_photo,
            "selfie_b64": req.selfie,
            "liked_colors": req.liked_colors,
            "selected_item_ids": req.selected_item_ids,
            "occasion": req.occasion,
            "notes": req.notes,
        },
    )
    parts = [types.Part(text=f"Check my outfit for: {req.occasion or 'an everyday outing'}.")]
    if req.outfit_photo:
        data, mime = decode_data_url(req.outfit_photo)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    message = types.Content(role="user", parts=parts)

    async def stream():
        try:
            async for event in runner.run_async(user_id=user_id, session_id=session_id,
                                                new_message=message):
                if event.author not in AGENTS or not event.content:
                    continue
                text = "".join(p.text or "" for p in event.content.parts if not p.thought)
                if text.strip():
                    yield json.dumps({"type": "agent", "agent": event.author, "text": text}) + "\n"
            session = await sessions.get_session(app_name=APP_NAME, user_id=user_id,
                                                 session_id=session_id)
            yield json.dumps({"type": "result", "result": build_result(session.state)}) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": error_message(exc)}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")

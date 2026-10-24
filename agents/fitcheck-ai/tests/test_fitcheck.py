"""Offline tests: colour engine + full ADK pipeline with a fake LLM (no Ollama needed).

Run:  pytest -q
"""

import asyncio
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.models.base_llm import BaseLlm  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402

from fitcheck_ai import color_engine as ce  # noqa: E402
from fitcheck_ai.wardrobe import generate_combos, load_wardrobe  # noqa: E402


def _img_data_url(rgb_fn, size=(200, 200)) -> str:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    for y in range(size[1]):
        for x in range(size[0]):
            arr[y, x] = rgb_fn(x, y)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# --- colour engine ---------------------------------------------------------

def test_white_balance_removes_warm_cast():
    # A neutral grey card shot under a warm bulb (R and G boosted)
    warm = _img_data_url(lambda x, y: (170, 140, 95))
    px, report = ce.correct_lighting(ce.decode_image(warm))
    r, g, b = px.reshape(-1, 3).mean(0)
    assert "warm" in report.cast
    # 80% correction strength by default (avoids neutralising genuinely coloured garments)
    assert max(r, g, b) - min(r, g, b) < (170 - 95) * 0.3, "cast should be mostly removed"


def test_selfie_skin_detection():
    # skin-ish centre on a dark background
    def fn(x, y):
        return (200, 150, 120) if 50 < x < 150 and 40 < y < 170 else (30, 25, 25)
    out = ce.analyze_selfie(_img_data_url(fn))
    assert out["skin"]["skin_hex"] is not None
    assert out["skin"]["season"] in {"Spring", "Summer", "Autumn", "Winter"}


def test_harmony_classification():
    assert ce.harmony_report(["#111111", "#f7f7f5"])["scheme"] == "all neutrals"
    assert ce.harmony_report(["#111111", "#c62828"])["scheme"] == "neutrals + one accent"


def test_combos_only_use_owned_items():
    wardrobe = load_wardrobe()
    ids = {i["id"] for i in wardrobe}
    combos = generate_combos(wardrobe, ["#9caf88", "#c19a6b"], "office meeting")
    assert 3 <= len(combos) <= 6
    assert all(p["id"] in ids for c in combos for p in c["items"])


# --- full pipeline with a fake Gemma ---------------------------------------

CANNED = {  # order matters: most specific role first
    "HEAD STYLIST": None,  # filled below
    "SHOPPING SKEPTIC": "C1, C2, C3. Nothing to buy.",
    "eyes of a fashion": "- White linen shirt, relaxed fit\n- Beige wide-leg pants",
    "PERSONAL STYLIST": "Balanced volumes; tuck the shirt. SCORE: 7/10",
    "COLOR EXPERT": "Soft neutral palette, low contrast. SCORE: 8/10",
    "OCCASION EXPERT": "Right for office; add a blazer. SCORE: 6/10",
    "COLOR ANALYST": "Hero colours: sage, camel. SCORE: 7/10",
}
CANNED["HEAD STYLIST"] = json.dumps({
        "verdict": "Clean and calm — add structure.",
        "scores": {"silhouette": 7, "color": 8, "occasion": 6, "palette_fit": 7},
        "overall_score": 7.1,
        "debate": [{"topic": "Blazer?", "resolution": "Yes, charcoal blazer."}],
        "improvements": ["Half-tuck the shirt", "Add the charcoal blazer", "Swap to loafers"],
        "alternatives": [{"combo_id": "C1", "why": "Polished"}, {"combo_id": "C9", "why": "bogus"}],
        "color_board": {"hero_colors": ["sage"], "avoid_near_face": ["mustard"], "tip": "Go soft."},
        "buy_next": "nothing — shop your closet",
})
SEEN_INSTRUCTIONS = []


class FakeGemma(BaseLlm):
    model: str = "fake-gemma"

    async def generate_content_async(self, llm_request, stream=False):
        si = str(llm_request.config.system_instruction or "")
        SEEN_INSTRUCTIONS.append(si)
        text = next((v for k, v in CANNED.items() if k in si), "ok")
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def _patch_models(agent):
    if isinstance(agent, LlmAgent):
        agent.model = FakeGemma()
    for sub in getattr(agent, "sub_agents", []) or []:
        _patch_models(sub)


def test_full_pipeline_end_to_end():
    import server

    _patch_models(server.root_agent)
    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    selfie = _img_data_url(lambda x, y: (205, 160, 125) if 50 < x < 150 else (40, 30, 30))
    resp = client.post("/api/fitcheck", json={
        "selfie": selfie, "liked_colors": ["#9caf88", "#c42f87"],
        "selected_item_ids": ["t1", "b3", "s2"], "occasion": "office meeting",
    })
    lines = [json.loads(l) for l in resp.text.strip().splitlines()]
    errors = [l for l in lines if l["type"] == "error"]
    assert not errors, errors
    agents = [l["agent"] for l in lines if l["type"] == "agent"]
    for name in ["ColorLab", "OutfitReader", "Stylist", "ColorExpert", "OccasionExpert",
                 "ColorAnalyst", "ShoppingSkeptic", "HeadStylist"]:
        assert name in agents, f"{name} did not speak"

    result = lines[-1]["result"]
    assert result["parsed_ok"]
    assert result["overall_score"] == 7.1
    assert [a["combo_id"] for a in result["alternatives"]] == ["C1"]  # bogus C9 dropped
    assert result["palette"]["colors"]
    # state templating actually injected the grounded facts into prompts
    assert any("White linen shirt" in s for s in SEEN_INSTRUCTIONS)
    assert not any("{outfit_notes}" in s for s in SEEN_INSTRUCTIONS)


def test_colorlab_endpoint():
    import server
    from fastapi.testclient import TestClient

    r = TestClient(server.app).post("/api/colorlab", json={"liked_colors": ["#2b4fbf"]})
    assert r.status_code == 200 and r.json()["palette"]["colors"]

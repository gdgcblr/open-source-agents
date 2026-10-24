"""Tests run offline: a fake Gemini client stands in for the API."""

import base64
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from google.adk.agents import LlmAgent
from google.genai import types
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import colors  # noqa: E402
import main  # noqa: E402
from wardrobe import generate_combos, load_wardrobe  # noqa: E402


def image_data_url(pixel_fn, size=(200, 200)) -> str:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    for y in range(size[1]):
        for x in range(size[0]):
            arr[y, x] = pixel_fn(x, y)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SCORECARD = {
    "verdict": "Clean and calm, needs structure.",
    "scores": {"silhouette": 7, "color": 8, "occasion": 6, "palette_fit": 7},
    "overall_score": 7.1,
    "debate": [{"topic": "Blazer?", "resolution": "Yes, the charcoal one."}],
    "improvements": ["Tuck the shirt", "Add the charcoal blazer", "Swap to loafers"],
    "alternatives": [{"combo_id": "C1", "why": "Polished"}, {"combo_id": "C9", "why": "made up"}],
    "color_board": {"hero_colors": ["sage"], "avoid_near_face": ["mustard"], "tip": "Go soft."},
    "buy_next": "nothing, shop your closet",
}

# Canned replies, matched on a phrase from each agent's instruction.
REPLIES = {
    "You lead the styling team": json.dumps(SCORECARD),
    "shopping skeptic": "C1, C2, C3. Nothing to buy.",
    "You describe outfits": "- White linen shirt, relaxed fit\n- Beige wide-leg pants",
    "You are the stylist": "Balanced volumes; tuck the shirt. SCORE: 7/10",
    "You are the colour expert": "Soft neutrals, low contrast. SCORE: 8/10",
    "You are the occasion expert": "Right for the office. SCORE: 6/10",
    "You are the colour analyst": "Hero colours: sage, camel. SCORE: 7/10",
}


class FakeGemini:
    """Just enough of google.genai.Client for ADK's Gemini model class."""

    def __init__(self, empty_for: str | None = None):
        self.calls = []
        self.empty_for = empty_for
        self.vertexai = False
        self._api_client = SimpleNamespace(vertexai=False, _http_options=types.HttpOptions())
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, model, contents, config):
        instruction = str(config.system_instruction or "")
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.empty_for and self.empty_for in instruction:
            # Gemma spent its whole budget thinking and returned no answer.
            parts = [types.Part(text="thinking...", thought=True)]
            finish = "MAX_TOKENS"
        else:
            reply = next((v for k, v in REPLIES.items() if k in instruction), "ok")
            parts = [types.Part(text="private reasoning", thought=True), types.Part(text=reply)]
            finish = "STOP"
        return types.GenerateContentResponse(candidates=[types.Candidate(
            finish_reason=finish, content=types.Content(role="model", parts=parts))])


@pytest.fixture
def fake_api():
    def install(**kwargs):
        fake = FakeGemini(**kwargs)

        def patch(agent):
            if isinstance(agent, LlmAgent):
                agent.model.client = fake
            for sub in agent.sub_agents or []:
                patch(sub)

        patch(main.root_agent)
        return fake
    return install


def run_fitcheck(payload: dict) -> list[dict]:
    resp = TestClient(main.app).post("/api/fitcheck", json=payload)
    return [json.loads(line) for line in resp.text.strip().splitlines()]


# Colour analysis

def test_white_balance_removes_warm_cast():
    warm_grey = image_data_url(lambda x, y: (170, 140, 95))
    pixels, report = colors.correct_lighting(colors.decode_image(warm_grey))
    r, g, b = pixels.reshape(-1, 3).mean(0)
    assert "warm" in report.cast
    assert max(r, g, b) - min(r, g, b) < 25


def test_selfie_skin_detection():
    face = image_data_url(lambda x, y: (200, 150, 120) if 50 < x < 150 and 40 < y < 170 else (30, 25, 25))
    skin = colors.analyze_selfie(face)["skin"]
    assert skin["skin_hex"] and skin["season"] in {"Spring", "Summer", "Autumn", "Winter"}


def test_harmony_classification():
    assert colors.harmony_report(["#111111", "#f7f7f5"])["scheme"] == "all neutrals"
    assert colors.harmony_report(["#111111", "#c62828"])["scheme"] == "neutrals + one accent"


def test_combos_only_use_owned_items():
    wardrobe = load_wardrobe()
    owned = {i["id"] for i in wardrobe}
    combos = generate_combos(wardrobe, ["#9caf88", "#c19a6b"], "office meeting")
    assert 3 <= len(combos) <= 6
    assert all(p["id"] in owned for c in combos for p in c["items"])


# Full pipeline

def test_full_council_run(fake_api):
    fake = fake_api()
    outfit = image_data_url(lambda x, y: (40, 50, 90) if y > 100 else (235, 230, 220))
    events = run_fitcheck({"outfit_photo": outfit, "liked_colors": ["#1f2a44"],
                           "occasion": "job interview"})

    assert not [e for e in events if e["type"] == "error"], events
    speakers = {e["agent"] for e in events if e["type"] == "agent"}
    assert speakers == main.AGENTS
    assert len(fake.calls) == 7
    assert {c["model"] for c in fake.calls} == {main.MODEL}

    # The photo reaches the outfit reader as image bytes.
    reader = next(c for c in fake.calls if "You describe outfits" in str(c["config"].system_instruction))
    mimes = [p.inline_data.mime_type for c in reader["contents"] for p in c.parts if p.inline_data]
    assert mimes == ["image/png"]

    # Thinking text never reaches the user.
    assert not any("private reasoning" in e.get("text", "") for e in events)

    result = events[-1]["result"]
    assert result["parsed_ok"] and result["overall_score"] == 7.1
    assert [a["combo_id"] for a in result["alternatives"]] == ["C1"]  # made-up C9 dropped


def test_empty_expert_answer_does_not_break_the_run(fake_api):
    fake_api(empty_for="You are the colour analyst")
    events = run_fitcheck({"selected_item_ids": ["t1", "b3", "s2"], "occasion": "office"})

    assert not [e for e in events if e["type"] == "error"], events
    analyst = next(e for e in events if e.get("agent") == "ColorAnalyst")
    assert "MAX_TOKENS" in analyst["text"]
    assert events[-1]["type"] == "result"


def test_palette_endpoint_and_health(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "secret-key-123")
    client = TestClient(main.app)
    assert client.post("/api/palette", json={"liked_colors": ["#2b4fbf"]}).json()["palette"]["colors"]
    assert "secret-key-123" not in client.get("/api/health").text

"""FitCheck AI — Your Personal Stylist Council (Gemma + Google ADK).

Pipeline (SequentialAgent):

  1. ColorLab          custom BaseAgent, pure Python: lighting-corrected colour
                       analysis of the selfie / outfit photo, personal palette,
                       wardrobe candidates. No LLM — facts, not guesses.
  2. OutfitReader      Gemma (vision): turns the outfit photo or wardrobe picks
                       into a precise garment description.
  3. StylistCouncil    ParallelAgent — four Gemma experts judge independently:
                         Stylist · Color Expert · Occasion Expert · Color Analyst
  4. ShoppingSkeptic   Gemma: picks alternatives ONLY from clothes you own.
  5. HeadStylist       Gemma: settles the debate → JSON scorecard.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from . import color_engine as ce
from .models import build_model, default_model, generation_config
from .wardrobe import describe_combos, describe_items, generate_combos, load_wardrobe

MODEL_ID = os.getenv("FITCHECK_MODEL") or default_model()
VISION_MODEL_ID = os.getenv("FITCHECK_VISION_MODEL") or MODEL_ID


def _model(model_id: str):
    return build_model(model_id)


def _cfg(temp: float = 0.6, model_id: str = MODEL_ID) -> types.GenerateContentConfig:
    return generation_config(model_id, temp)


OUTPUT_KEYS = ["outfit_notes", "stylist_take", "color_take", "occasion_take",
               "analyst_take", "skeptic_take", "scorecard_raw"]
NO_ANSWER = "(no answer from this expert — ignore and decide without it)"


def _ensure_answer(callback_context, llm_response: LlmResponse):
    """after_model_callback: if Gemma returns only thinking (or nothing) — e.g. it
    hit the token limit — replace it with a visible placeholder, so the UI shows
    what happened and the next agents' {templates} still resolve."""
    parts = llm_response.content.parts if llm_response.content else []
    if llm_response.partial or any(p.text and p.text.strip() and not p.thought for p in parts) \
            or any(p.function_call for p in parts):
        return None
    reason = str(llm_response.finish_reason or llm_response.error_code or "empty response")
    hint = " (hit the token limit — raise FITCHECK_MAX_TOKENS)" if "MAX_TOKENS" in reason else ""
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(
        text=f"(no answer: {reason.split('.')[-1]}{hint})")]))


# ---------------------------------------------------------------------------
# 1. ColorLab — deterministic analysis step (custom ADK agent)
# ---------------------------------------------------------------------------

class ColorLab(BaseAgent):
    """Measures colours in code and writes grounded facts into session state."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        s = ctx.session.state
        liked = [h for h in s.get("liked_colors", []) if isinstance(h, str)]
        occasion = s.get("occasion") or "an everyday outing"
        wardrobe = load_wardrobe()
        selected_ids = set(s.get("selected_item_ids", []))
        selected = [i for i in wardrobe if i["id"] in selected_ids]

        selfie = ce.analyze_selfie(s["selfie_b64"]) if s.get("selfie_b64") else None
        photo = ce.analyze_outfit_photo(s["outfit_photo_b64"]) if s.get("outfit_photo_b64") else None

        skin = ce.SkinReport(**selfie["skin"]) if selfie else None
        palette = ce.build_palette(skin, liked)
        palette_hexes = [c["hex"] for c in palette["colors"]]

        if photo:
            outfit_hexes = [c["hex"] for c in photo["colors"]]
            harmony = photo["harmony"]
            outfit_text = "Outfit comes from an uploaded photo (see image)."
            colors_text = ", ".join(f"{c['name']} {c['hex']} ({int(c['share'] * 100)}% of frame)"
                                    for c in photo["colors"])
        elif selected:
            outfit_hexes = [i["hex"] for i in selected]
            harmony = ce.harmony_report(outfit_hexes)
            outfit_text = "Outfit picked from the digital wardrobe:\n" + describe_items(selected)
            colors_text = ", ".join(f"{i['color_name']} {i['hex']}" for i in selected)
        else:
            outfit_hexes, harmony = [], {"scheme": "n/a", "value_contrast": "n/a",
                                         "accent_count": 0, "rule_based_harmony_score": 0}
            outfit_text = "No outfit given — focus on palette and wardrobe suggestions."
            colors_text = "none"

        in_palette = [ce.name_color(h) for h in outfit_hexes
                      if ce.is_neutral(h) or min(ce.delta_e(h, p) for p in palette_hexes) < 28]

        combos = generate_combos(wardrobe, palette_hexes, occasion, exclude_ids=selected_ids or None)

        lighting_bits = []
        for label, rep in (("Selfie", selfie), ("Outfit photo", photo)):
            if rep:
                L = rep["lighting"]
                lighting_bits.append(f"{label}: {L['cast']}, exposure {L['exposure']}, "
                                     f"colour confidence {int(L['confidence'] * 100)}%.")
        if skin and skin.skin_hex:
            skin_text = (f"Skin {skin.skin_hex}: {skin.undertone} undertone, {skin.depth} depth, "
                         f"{skin.contrast} contrast → closest season: {skin.season}.")
        else:
            skin_text = "No usable selfie — palette is built from the user's favourite colours."

        color_lab = {
            "selfie": selfie, "outfit_photo": photo, "palette": palette,
            "outfit_hexes": outfit_hexes, "harmony": harmony, "combos": combos,
            "selected_items": selected,
        }
        delta = {
            **{k: NO_ANSWER for k in OUTPUT_KEYS},  # safety net for {templates}
            "scorecard_raw": "",
            "color_lab": color_lab,
            "occasion_text": occasion,
            "user_notes": s.get("notes") or "none",
            "outfit_text": outfit_text,
            "outfit_colors_text": colors_text,
            "harmony_text": (f"scheme: {harmony['scheme']}, value contrast: {harmony['value_contrast']}, "
                             f"accent colours: {harmony['accent_count']}, rule-based harmony "
                             f"{harmony['rule_based_harmony_score']}/10"),
            "skin_text": skin_text,
            "lighting_text": " ".join(lighting_bits) or "No photos — no lighting correction needed.",
            "palette_text": f"{palette['source']}: " + ", ".join(
                f"{c['name']} {c['hex']}" for c in palette["colors"]),
            "liked_text": ", ".join(
                f"{l['name']} ({'suits' if l['fits_palette'] else 'outside'} palette)"
                for l in palette["liked_colors"]) or "none given",
            "in_palette_text": ", ".join(in_palette) or "none",
            "wardrobe_text": describe_items(wardrobe),
            "combos_text": describe_combos(combos),
        }
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(
                text=f"Color lab ready. {skin_text} Outfit colours: {colors_text}.")]),
            actions=EventActions(state_delta=delta),
        )


# ---------------------------------------------------------------------------
# 2. OutfitReader — Gemma vision
# ---------------------------------------------------------------------------

outfit_reader = LlmAgent(
    name="OutfitReader",
    model=_model(VISION_MODEL_ID),
    generate_content_config=_cfg(0.2, VISION_MODEL_ID),
    instruction="""You are the eyes of a fashion stylist council.
{outfit_text}
Measured colours (lighting-corrected, trust these over how the image looks): {outfit_colors_text}

Describe the outfit precisely in 4-6 short bullet points: each garment (type, fit,
length, fabric/texture if visible), how pieces are layered, the overall silhouette,
footwear and accessories. If something isn't visible, say "not visible".
No opinions or scores — only observations.""",
    output_key="outfit_notes",
    after_model_callback=_ensure_answer,
)

# ---------------------------------------------------------------------------
# 3. The council — four independent experts in parallel
# ---------------------------------------------------------------------------

_COMMON = """
OUTFIT: {outfit_notes}
OCCASION: {occasion_text}
USER NOTES: {user_notes}
Be specific and kind but honest. Max 90 words. End with exactly one line:
SCORE: <number 1-10>/10"""

stylist = LlmAgent(
    name="Stylist",
    model=_model(MODEL_ID), generate_content_config=_cfg(), include_contents="none",
    instruction="""You are the PERSONAL STYLIST on the council. Judge ONLY proportions,
layering and silhouette: balance of volume top vs bottom, waist definition, lengths,
how layers stack, fit. Give 1 strength and 2 concrete fixes.""" + _COMMON,
    output_key="stylist_take",
    after_model_callback=_ensure_answer,
)

color_expert = LlmAgent(
    name="ColorExpert",
    model=_model(MODEL_ID), generate_content_config=_cfg(), include_contents="none",
    instruction="""You are the COLOR EXPERT on the council. Judge ONLY colour harmony and contrast.
Measured outfit colours: {outfit_colors_text}
Rule-based harmony analysis: {harmony_text}
Colours that sit in the wearer's personal palette: {in_palette_text}
Wearer's palette: {palette_text}
Explain the scheme in plain words, whether contrast suits the wearer, and one colour swap.""" + _COMMON,
    output_key="color_take",
    after_model_callback=_ensure_answer,
)

occasion_expert = LlmAgent(
    name="OccasionExpert",
    model=_model(MODEL_ID), generate_content_config=_cfg(), include_contents="none",
    instruction="""You are the OCCASION EXPERT on the council. Judge ONLY whether the look suits
the event: formality level, practicality (weather, walking, sitting, dancing),
cultural context and dress codes common in India where relevant. Say what to
add/remove to hit the dress code exactly.""" + _COMMON,
    output_key="occasion_take",
    after_model_callback=_ensure_answer,
)

color_analyst = LlmAgent(
    name="ColorAnalyst",
    model=_model(MODEL_ID), generate_content_config=_cfg(), include_contents="none",
    instruction="""You are the COLOR ANALYST (ShadeMatch). Build the wearer's personal colour story.
Selfie analysis: {skin_text}
Lighting & camera notes: {lighting_text}
Personal palette: {palette_text}
Favourite colours: {liked_text}

In max 100 words: name their 4 hero colours from the palette, 2 colours to keep
away from the face, and how to wear favourites that fall outside the palette
(e.g. as trousers/shoes rather than near the face). If colour confidence is
below 60%, say the reading is tentative and suggest retaking in daylight.
End with exactly one line: SCORE: <how well the current outfit fits their palette, 1-10>/10""",
    output_key="analyst_take",
    after_model_callback=_ensure_answer,
)

council = ParallelAgent(
    name="StylistCouncil",
    sub_agents=[stylist, color_expert, occasion_expert, color_analyst],
)

# ---------------------------------------------------------------------------
# 4. Shopping Skeptic — wardrobe-first alternatives
# ---------------------------------------------------------------------------

shopping_skeptic = LlmAgent(
    name="ShoppingSkeptic",
    model=_model(MODEL_ID), generate_content_config=_cfg(0.4), include_contents="none",
    instruction="""You are the SHOPPING SKEPTIC. You believe the best outfit is usually already
in the closet. Occasion: {occasion_text}. Palette: {palette_text}

Council feedback on the current look:
- Stylist: {stylist_take}
- Color: {color_take}
- Occasion: {occasion_take}

Pre-matched combinations from the user's OWN wardrobe:
{combos_text}

Pick the 3 best combo IDs for this occasion and say in one line each why.
Then say whether ONE new purchase is truly justified (a real gap) or "nothing to buy".
Never invent garments that aren't listed. Max 110 words.""",
    output_key="skeptic_take",
    after_model_callback=_ensure_answer,
)

# ---------------------------------------------------------------------------
# 5. Head Stylist — settles the debate, outputs the scorecard
# ---------------------------------------------------------------------------

head_stylist = LlmAgent(
    name="HeadStylist",
    model=_model(MODEL_ID), generate_content_config=_cfg(0.3), include_contents="none",
    instruction="""You are the HEAD STYLIST chairing the council. Read every opinion, resolve
disagreements, and produce the final verdict.

OUTFIT: {outfit_notes}
OCCASION: {occasion_text}
STYLIST: {stylist_take}
COLOR EXPERT: {color_take}
OCCASION EXPERT: {occasion_take}
COLOR ANALYST: {analyst_take}
SHOPPING SKEPTIC: {skeptic_take}

Reply with ONLY valid JSON (no markdown fences), exactly this shape:
{
  "verdict": "<one punchy sentence>",
  "scores": {"silhouette": <1-10>, "color": <1-10>, "occasion": <1-10>, "palette_fit": <1-10>},
  "overall_score": <1-10, one decimal>,
  "debate": [{"topic": "<where experts disagreed or overlapped>", "resolution": "<your call>"}],
  "improvements": ["<concrete fix>", "<concrete fix>", "<concrete fix>"],
  "alternatives": [{"combo_id": "<C1..C6 from the skeptic>", "why": "<one line>"}],
  "color_board": {"hero_colors": ["<name>"], "avoid_near_face": ["<name>"], "tip": "<one line>"},
  "buy_next": "<one item or 'nothing — shop your closet'>"
}""",
    output_key="scorecard_raw",
    after_model_callback=_ensure_answer,
)

root_agent = SequentialAgent(
    name="FitCheckCouncil",
    description="Personal stylist council + colour analysis, powered by Gemma.",
    sub_agents=[ColorLab(name="ColorLab"), outfit_reader, council, shopping_skeptic, head_stylist],
)

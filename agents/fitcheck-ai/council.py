"""The FitCheck council: a Google ADK pipeline running on Gemma.

    ColorLab        plain Python: colour analysis, palette, wardrobe combos
    OutfitReader    describes the outfit (Gemma vision)
    StylistCouncil  four experts in parallel: stylist, colour, occasion, palette
    ShoppingSkeptic picks alternatives from the user's own wardrobe
    HeadStylist     settles the debate and writes the JSON scorecard
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.genai import types

import colors
import prompts
from wardrobe import describe_combos, describe_items, generate_combos, load_wardrobe

MODEL = os.getenv("FITCHECK_MODEL", "gemma-4-26b-a4b-it")

# Free-tier quotas are per minute and the council sends four requests at once,
# so retry rate limits and transient server errors with backoff.
RETRY = types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=30.0,
                               http_status_codes=[408, 429, 500, 502, 503, 504])

OUTPUT_KEYS = ["outfit_notes", "stylist_take", "color_take", "occasion_take",
               "analyst_take", "skeptic_take"]


def generation_config(temperature: float) -> types.GenerateContentConfig:
    # Gemma 4 thinks before answering, and the thinking shares the output budget.
    # Short styling answers don't need much of it, and keeping it minimal
    # avoids empty replies and makes each run a lot faster.
    return types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=4096,
        thinking_config=types.ThinkingConfig(thinking_level="minimal"),
    )


def ensure_answer(callback_context, llm_response: LlmResponse) -> LlmResponse | None:
    """Replace an empty model reply with a short note, so the next agents still run."""
    parts = llm_response.content.parts if llm_response.content else []
    if llm_response.partial or any(p.text and p.text.strip() and not p.thought for p in parts):
        return None
    reason = str(llm_response.finish_reason or "empty response").split(".")[-1]
    return LlmResponse(content=types.Content(
        role="model", parts=[types.Part(text=f"(no answer: {reason})")]))


def expert(name: str, instruction: str, output_key: str, temperature: float = 0.6,
           sees_photo: bool = False) -> LlmAgent:
    # Only the outfit reader needs the user's message (it carries the photo);
    # everyone else works from session state.
    return LlmAgent(
        name=name,
        model=Gemini(model=MODEL, retry_options=RETRY),
        instruction=instruction,
        generate_content_config=generation_config(temperature),
        include_contents="default" if sees_photo else "none",
        output_key=output_key,
        after_model_callback=ensure_answer,
    )


class ColorLab(BaseAgent):
    """Measures colours and builds the wardrobe options, then writes them to session state."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        liked = [h for h in state.get("liked_colors", []) if isinstance(h, str)]
        occasion = state.get("occasion") or "an everyday outing"
        wardrobe = load_wardrobe()
        selected_ids = set(state.get("selected_item_ids", []))
        selected = [i for i in wardrobe if i["id"] in selected_ids]

        selfie = colors.analyze_selfie(state["selfie_b64"]) if state.get("selfie_b64") else None
        photo = colors.analyze_outfit_photo(state["outfit_photo_b64"]) if state.get("outfit_photo_b64") else None
        skin = colors.SkinReport(**selfie["skin"]) if selfie else None
        palette = colors.build_palette(skin, liked)
        palette_hexes = [c["hex"] for c in palette["colors"]]

        if photo:
            outfit_hexes = [c["hex"] for c in photo["colors"]]
            harmony = photo["harmony"]
            outfit_text = "The outfit is in the uploaded photo."
            colors_text = ", ".join(f"{c['name']} {c['hex']} ({int(c['share'] * 100)}% of frame)"
                                    for c in photo["colors"])
        elif selected:
            outfit_hexes = [i["hex"] for i in selected]
            harmony = colors.harmony_report(outfit_hexes)
            outfit_text = "Outfit picked from the wardrobe:\n" + describe_items(selected)
            colors_text = ", ".join(f"{i['color_name']} {i['hex']}" for i in selected)
        else:
            outfit_hexes = []
            harmony = {"scheme": "n/a", "value_contrast": "n/a", "accent_count": 0,
                       "rule_based_harmony_score": 0}
            outfit_text = "No outfit given. Focus on the palette and wardrobe suggestions."
            colors_text = "none"

        in_palette = [colors.name_color(h) for h in outfit_hexes
                      if colors.is_neutral(h) or min(colors.delta_e(h, p) for p in palette_hexes) < 28]
        combos = generate_combos(wardrobe, palette_hexes, occasion, exclude_ids=selected_ids or None)

        lighting = []
        for label, report in (("Selfie", selfie), ("Outfit photo", photo)):
            if report:
                light = report["lighting"]
                lighting.append(f"{label}: {light['cast']}, {light['exposure']} exposure, "
                                f"colour confidence {int(light['confidence'] * 100)}%.")
        if skin and skin.skin_hex:
            skin_text = (f"Skin {skin.skin_hex}: {skin.undertone} undertone, {skin.depth} depth, "
                         f"{skin.contrast} contrast, closest season {skin.season}.")
        else:
            skin_text = "No usable selfie, so the palette is built from the user's favourite colours."

        delta = {
            # Defaults so later prompts still render if an expert fails to answer.
            **{key: "(no answer)" for key in OUTPUT_KEYS},
            "scorecard_raw": "",
            "color_lab": {"selfie": selfie, "outfit_photo": photo, "palette": palette,
                          "harmony": harmony, "combos": combos},
            "occasion_text": occasion,
            "user_notes": state.get("notes") or "none",
            "outfit_text": outfit_text,
            "outfit_colors_text": colors_text,
            "harmony_text": (f"{harmony['scheme']}, {harmony['value_contrast']} value contrast, "
                             f"{harmony['accent_count']} accent colours, "
                             f"rule-based score {harmony['rule_based_harmony_score']}/10"),
            "skin_text": skin_text,
            "lighting_text": " ".join(lighting) or "No photos.",
            "palette_text": f"{palette['source']}: " + ", ".join(
                f"{c['name']} {c['hex']}" for c in palette["colors"]),
            "liked_text": ", ".join(
                f"{c['name']} ({'in' if c['fits_palette'] else 'outside'} palette)"
                for c in palette["liked_colors"]) or "none given",
            "in_palette_text": ", ".join(in_palette) or "none",
            "wardrobe_text": describe_items(wardrobe),
            "combos_text": describe_combos(combos),
        }
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(
                text=f"{skin_text} Outfit colours: {colors_text}.")]),
            actions=EventActions(state_delta=delta),
        )


root_agent = SequentialAgent(
    name="FitCheckCouncil",
    sub_agents=[
        ColorLab(name="ColorLab"),
        expert("OutfitReader", prompts.OUTFIT_READER, "outfit_notes", temperature=0.2, sees_photo=True),
        ParallelAgent(name="StylistCouncil", sub_agents=[
            expert("Stylist", prompts.STYLIST, "stylist_take"),
            expert("ColorExpert", prompts.COLOR_EXPERT, "color_take"),
            expert("OccasionExpert", prompts.OCCASION_EXPERT, "occasion_take"),
            expert("ColorAnalyst", prompts.COLOR_ANALYST, "analyst_take"),
        ]),
        expert("ShoppingSkeptic", prompts.SHOPPING_SKEPTIC, "skeptic_take", temperature=0.4),
        expert("HeadStylist", prompts.HEAD_STYLIST, "scorecard_raw", temperature=0.3),
    ],
)

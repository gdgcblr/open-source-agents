"""Deterministic color science for FitCheck AI.

The LLM agents never "eyeball" raw pixels for color facts. Instead this module
measures colors in code — after correcting for lighting and camera differences —
and hands the agents grounded numbers to reason about.

Lighting / camera handling:
  1. Gray-world white balance (with clipped-pixel rejection) removes color casts
     from warm bulbs, cool daylight, or phone camera tuning.
  2. Exposure normalisation pulls median luminance toward a neutral mid-grey.
  3. A confidence score drops when the photo is very dark, blown out, or had a
     strong cast — and the agents are told to hedge accordingly.
"""

from __future__ import annotations

import base64
import io
import math
from functools import lru_cache
from dataclasses import dataclass, field, asdict

import numpy as np
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Colour conversions
# ---------------------------------------------------------------------------

def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (int(max(0, min(255, round(float(c))))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(rgb) -> np.ndarray:
    """sRGB (0-255) -> CIE Lab (D65). Accepts shape (..., 3)."""
    arr = np.asarray(rgb, dtype=np.float64)
    lin = _srgb_to_linear(arr)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    eps, k = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (k * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


@lru_cache(maxsize=65536)
def delta_e(hex1: str, hex2: str) -> float:
    """CIE76 colour difference (good enough for wardrobe matching)."""
    l1, l2 = rgb_to_lab(hex_to_rgb(hex1)), rgb_to_lab(hex_to_rgb(hex2))
    return float(np.linalg.norm(l1 - l2))


def hex_to_hsl(h: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in hex_to_rgb(h))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        hue = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return hue * 60, s, l


def hsl_to_hex(hue: float, s: float, l: float) -> str:
    hue = hue % 360
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = l - c / 2
    seg = int(hue // 60)
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][seg % 6]
    return rgb_to_hex(((r + m) * 255, (g + m) * 255, (b + m) * 255))


# ---------------------------------------------------------------------------
# Colour naming
# ---------------------------------------------------------------------------

NAMED_COLORS: dict[str, str] = {
    "black": "#111111", "charcoal": "#36454f", "grey": "#8e8e8e", "light grey": "#cfcfcf",
    "white": "#f7f7f5", "ivory": "#f4efe1", "cream": "#efe3c8", "beige": "#d9c4a3",
    "camel": "#c19a6b", "tan": "#b98b5e", "brown": "#6b4423", "chocolate": "#3f2a1d",
    "navy": "#1f2a44", "royal blue": "#2b4fbf", "cobalt": "#0047ab", "sky blue": "#8ec5e8",
    "powder blue": "#b9d3ea", "denim": "#4f6d8f", "teal": "#11777a", "turquoise": "#2fc2b8",
    "emerald": "#0f7a4f", "olive": "#6b6b2a", "sage": "#9caf88", "mint": "#b6e3c6",
    "forest green": "#22492f", "mustard": "#d4a72c", "yellow": "#f2d22e", "butter": "#f6e7a1",
    "orange": "#e8772e", "rust": "#a5472a", "terracotta": "#c46a4a", "coral": "#ee7c6b",
    "peach": "#f6b896", "blush": "#e8b4b0", "pink": "#ee8fb3", "fuchsia": "#c42f87",
    "red": "#c62828", "burgundy": "#6d1a2d", "wine": "#5a1f2e", "maroon": "#6a1b1b",
    "lavender": "#b9a6d9", "lilac": "#c8a2c8", "purple": "#6a3d9a", "plum": "#5e2a4f",
    "mauve": "#a6788c", "gold": "#c9a227", "silver": "#bfc1c2", "khaki": "#bdb07a",
}


@lru_cache(maxsize=4096)
def name_color(hex_color: str) -> str:
    return min(NAMED_COLORS, key=lambda n: delta_e(hex_color, NAMED_COLORS[n]))


@lru_cache(maxsize=4096)
def is_neutral(hex_color: str) -> bool:
    _, s, l = hex_to_hsl(hex_color)
    name = name_color(hex_color)
    neutral_names = {"black", "charcoal", "grey", "light grey", "white", "ivory", "cream",
                     "beige", "camel", "tan", "navy", "denim", "khaki", "brown", "chocolate"}
    return s < 0.15 or l < 0.12 or l > 0.93 or name in neutral_names


# ---------------------------------------------------------------------------
# Image loading + lighting correction
# ---------------------------------------------------------------------------

@dataclass
class LightingReport:
    cast: str              # e.g. "warm (yellow/orange) cast" or "neutral"
    cast_strength: float   # 0..1
    exposure: str          # "dark", "balanced", "bright"
    confidence: float      # 0..1 — how much to trust colour readings
    notes: list[str] = field(default_factory=list)


def decode_image(data: bytes | str) -> Image.Image:
    if isinstance(data, str):
        if "," in data and data.strip().startswith("data:"):
            data = data.split(",", 1)[1]
        data = base64.b64decode(data)
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((320, 320))
    return img


def _skin_mask(flat: np.ndarray) -> np.ndarray:
    r, g, b = flat[:, 0], flat[:, 1], flat[:, 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cr = (r - y) * 0.713 + 128
    cb = (b - y) * 0.564 + 128
    return (cr > 135) & (cr < 180) & (cb > 85) & (cb < 135) & (y > 40)


def correct_lighting(img: Image.Image, exclude_skin: bool = False,
                     strength: float = 0.8) -> tuple[np.ndarray, LightingReport]:
    px = np.asarray(img, dtype=np.float64)
    flat = px.reshape(-1, 3)
    lum = flat @ np.array([0.2126, 0.7152, 0.0722])

    # Reject clipped / near-black pixels when estimating the illuminant.
    usable = (lum > 20) & (flat.max(axis=1) < 250)
    if exclude_skin:
        # In a selfie, skin dominates the frame; gray-world on skin would "correct"
        # away the very warmth we're trying to measure. Estimate light from the rest.
        bg = usable & ~_skin_mask(flat)
        if bg.sum() > 0.15 * len(flat):
            usable = bg
        else:
            strength = 0.35  # mostly skin in frame → only correct gently
    sample = flat[usable] if usable.sum() > 200 else flat
    means = sample.mean(axis=0)
    gray = means.mean()
    gains = gray / np.maximum(means, 1e-6)
    gains = np.clip(1 + (gains - 1) * strength, 0.6, 1.6)  # don't over-correct

    balanced = np.clip(flat * gains, 0, 255)

    # Exposure: pull median luminance toward ~118 (mid-grey in sRGB).
    # Judged on the same reference pixels as the illuminant (the background, for
    # selfies), so a deep skin tone isn't mistaken for an underexposed photo.
    ref = balanced[usable] if usable.sum() > 200 else balanced
    med = float(np.median(ref @ np.array([0.2126, 0.7152, 0.0722])))
    # Only touch exposure when the shot is clearly mis-exposed — otherwise we'd
    # erase real differences in skin depth / garment lightness.
    if med < 90:
        exp_gain = float(np.clip(118 / max(med, 1), 1.0, 1.8))
    elif med > 185:
        exp_gain = float(np.clip(160 / med, 0.7, 1.0))
    else:
        exp_gain = 1.0
    # ...but never push the bright subject (face, light garments) into clipping.
    p98 = float(np.percentile(balanced.max(axis=1), 98))
    exp_gain = min(exp_gain, max(1.0, 245 / max(p98, 1)))
    corrected = np.clip(balanced * exp_gain, 0, 255).reshape(px.shape)

    # Describe what we corrected.
    r, g, b = means / max(gray, 1e-6)
    cast_strength = float(min(1.0, (abs(r - b) + abs(g - (r + b) / 2)) / 0.6))
    if cast_strength < 0.12:
        cast = "neutral"
    elif r > b and g >= b:
        cast = "warm (yellow/orange) cast — likely indoor bulb light"
    elif b > r:
        cast = "cool (blue) cast — likely shade, overcast or LED light"
    elif g > max(r, b):
        cast = "green tint — likely fluorescent light"
    else:
        cast = "magenta tint"

    exposure = "dark" if med < 90 else "bright" if med > 185 else "balanced"
    clipped = float((flat.max(axis=1) >= 250).mean())

    confidence = 1.0
    notes = []
    if exposure == "dark":
        confidence -= 0.3
        notes.append("Photo is underexposed; colours may read deeper than in person.")
    if exposure == "bright" or clipped > 0.15:
        confidence -= 0.25
        notes.append("Highlights are blown out; pale colours may be lost.")
    confidence -= 0.5 * cast_strength  # the stronger the cast, the less certain the fix
    if cast_strength > 0.5:
        notes.append("Strong colour cast was corrected; true colours may differ slightly.")
    if cast != "neutral":
        notes.append(f"Detected {cast}; white balance was auto-corrected.")
    notes.append("For best accuracy: daylight near a window, no flash, no beauty filters.")

    return corrected, LightingReport(cast, round(cast_strength, 2), exposure,
                                     round(max(0.2, confidence), 2), notes)


# ---------------------------------------------------------------------------
# Dominant colours (tiny k-means, no sklearn needed)
# ---------------------------------------------------------------------------

def dominant_colors(pixels: np.ndarray, k: int = 5, seed: int = 7) -> list[dict]:
    flat = pixels.reshape(-1, 3)
    if len(flat) > 6000:
        rng = np.random.default_rng(seed)
        flat = flat[rng.choice(len(flat), 6000, replace=False)]
    lab = rgb_to_lab(flat)
    rng = np.random.default_rng(seed)
    centers = lab[rng.choice(len(lab), k, replace=False)]
    for _ in range(15):
        d = ((lab[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        labels = d.argmin(1)
        new = np.array([lab[labels == i].mean(0) if (labels == i).any() else centers[i]
                        for i in range(k)])
        if np.allclose(new, centers, atol=0.5):
            break
        centers = new
    out = []
    for i in range(k):
        mask = labels == i
        if not mask.any():
            continue
        hx = rgb_to_hex(flat[mask].mean(0))
        out.append({"hex": hx, "name": name_color(hx), "share": round(float(mask.mean()), 3)})
    # merge clusters that got the same name
    merged: dict[str, dict] = {}
    for c in sorted(out, key=lambda c: -c["share"]):
        if c["name"] in merged:
            merged[c["name"]]["share"] = round(merged[c["name"]]["share"] + c["share"], 3)
        else:
            merged[c["name"]] = c
    return sorted(merged.values(), key=lambda c: -c["share"])


def center_crop(px: np.ndarray, frac: float = 0.7) -> np.ndarray:
    h, w = px.shape[:2]
    dh, dw = int(h * (1 - frac) / 2), int(w * (1 - frac) / 2)
    return px[dh:h - dh, dw:w - dw]


# ---------------------------------------------------------------------------
# Selfie -> undertone / depth / contrast
# ---------------------------------------------------------------------------

@dataclass
class SkinReport:
    skin_hex: str | None
    undertone: str        # warm / cool / neutral / unknown
    depth: str            # light / medium / deep / unknown
    contrast: str         # low / medium / high / unknown
    season: str           # Spring / Summer / Autumn / Winter / unknown
    skin_pixel_share: float


def analyze_skin(px: np.ndarray) -> SkinReport:
    flat = px.reshape(-1, 3)
    mask = _skin_mask(flat)
    share = float(mask.mean())
    if mask.sum() < 150:
        return SkinReport(None, "unknown", "unknown", "unknown", "unknown", round(share, 3))

    skin = np.median(flat[mask], axis=0)
    L, a, bb = rgb_to_lab(skin)
    hue = math.degrees(math.atan2(bb, a))
    undertone = "warm" if hue > 58 else "cool" if hue < 47 else "neutral"
    depth = "light" if L > 68 else "medium" if L > 48 else "deep"

    # Contrast: skin vs the darkest features in frame (hair, brows, eyes).
    all_L = rgb_to_lab(flat)[:, 0]
    dark_L = float(np.percentile(all_L, 8))
    gap = L - dark_L
    contrast = "high" if gap > 45 else "medium" if gap > 25 else "low"

    warmish = undertone in ("warm", "neutral") and hue >= 52
    if warmish:
        # light & bright → Spring; deep or muted → Autumn
        season = "Spring" if depth == "light" or (depth == "medium" and contrast == "high") else "Autumn"
    else:
        # deep or high-contrast → Winter; soft & light → Summer
        season = "Winter" if contrast == "high" or depth == "deep" else "Summer"

    return SkinReport(rgb_to_hex(skin), undertone, depth, contrast, season, round(share, 3))


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

SEASON_PALETTES: dict[str, list[str]] = {
    "Spring": ["#f6b896", "#ee7c6b", "#f2d22e", "#2fc2b8", "#9caf88", "#c19a6b", "#f4efe1", "#2b4fbf"],
    "Summer": ["#b9d3ea", "#e8b4b0", "#b9a6d9", "#a6788c", "#9caf88", "#4f6d8f", "#cfcfcf", "#1f2a44"],
    "Autumn": ["#a5472a", "#d4a72c", "#6b6b2a", "#c46a4a", "#11777a", "#6b4423", "#efe3c8", "#22492f"],
    "Winter": ["#111111", "#f7f7f5", "#c62828", "#0047ab", "#0f7a4f", "#c42f87", "#6d1a2d", "#36454f"],
}


def palette_from_liked(liked: list[str]) -> list[str]:
    """No selfie? Build a harmonious palette around colours the user loves."""
    palette: list[str] = []
    for hx in liked[:3]:
        h, s, l = hex_to_hsl(hx)
        palette += [hx,
                    hsl_to_hex(h + 30, s * 0.85, min(0.85, l + 0.1)),   # analogous, lighter
                    hsl_to_hex(h + 180, s * 0.7, l)]                     # complementary accent
    palette += ["#f4efe1", "#1f2a44"]  # anchor neutrals
    seen, uniq = set(), []
    for p in palette:
        n = name_color(p)
        if n not in seen:
            seen.add(n)
            uniq.append(p)
    return uniq[:9]


def build_palette(skin: SkinReport | None, liked: list[str]) -> dict:
    base = SEASON_PALETTES.get(skin.season, []) if skin and skin.season != "unknown" else []
    if base:
        palette = list(base)
        liked_fit = []
        for hx in liked:
            closest = min(base, key=lambda p: delta_e(p, hx))
            d = delta_e(closest, hx)
            fits = d < 28
            liked_fit.append({"hex": hx, "name": name_color(hx), "fits_palette": fits,
                              "closest_palette_color": name_color(closest)})
            if fits and name_color(hx) not in {name_color(p) for p in palette}:
                palette.append(hx)
        source = f"{skin.season} palette from selfie (+ your favourites that suit you)"
    elif liked:
        palette = palette_from_liked(liked)
        liked_fit = [{"hex": h, "name": name_color(h), "fits_palette": True,
                      "closest_palette_color": name_color(h)} for h in liked]
        source = "harmony rules built around the colours you love"
    else:
        palette = ["#f4efe1", "#1f2a44", "#c19a6b", "#9caf88", "#a6788c", "#4f6d8f"]
        liked_fit = []
        source = "versatile default palette (add a selfie or favourite colours to personalise)"
    return {
        "source": source,
        "colors": [{"hex": p, "name": name_color(p)} for p in palette],
        "liked_colors": liked_fit,
    }


# ---------------------------------------------------------------------------
# Outfit colour harmony
# ---------------------------------------------------------------------------

def harmony_report(hexes: list[str]) -> dict:
    """Classify the colour relationship of an outfit's key colours."""
    return dict(_harmony(tuple(hexes)))


@lru_cache(maxsize=8192)
def _harmony(hexes: tuple[str, ...]) -> tuple:
    hexes = list(hexes)
    accents = [h for h in hexes if not is_neutral(h)]
    labs = [rgb_to_lab(hex_to_rgb(h)) for h in hexes]
    l_spread = (max(l[0] for l in labs) - min(l[0] for l in labs)) if labs else 0
    contrast = "high" if l_spread > 55 else "medium" if l_spread > 25 else "low"

    if len(accents) == 0:
        scheme, score = "all neutrals", 7.5
    elif len(accents) == 1:
        scheme, score = "neutrals + one accent", 8.5
    else:
        hues = sorted(hex_to_hsl(h)[0] for h in accents)
        diffs = []
        for i in range(len(hues)):
            for j in range(i + 1, len(hues)):
                d = abs(hues[i] - hues[j])
                diffs.append(min(d, 360 - d))
        mx = max(diffs)
        if mx < 20:
            scheme, score = "monochromatic", 8.5
        elif mx < 60:
            scheme, score = "analogous", 8.0
        elif 150 <= mx <= 210 and len(accents) == 2:
            scheme, score = "complementary", 7.5
        elif len(accents) >= 3 and all(100 <= d <= 140 or d >= 200 for d in diffs):
            scheme, score = "triadic", 6.5
        else:
            scheme, score = "mixed / potentially clashing", 5.0
        if len(accents) >= 4:
            score -= 1.5
    return (("scheme", scheme), ("value_contrast", contrast), ("accent_count", len(accents)),
            ("rule_based_harmony_score", round(max(1.0, min(10.0, score)), 1)))


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def analyze_selfie(data: bytes | str) -> dict:
    img = decode_image(data)
    px, lighting = correct_lighting(img, exclude_skin=True)
    skin = analyze_skin(center_crop(px, 0.8))
    if skin.skin_hex is None:
        lighting.notes.append("Couldn't find enough skin in the selfie — using your favourite colours instead.")
        lighting.confidence = min(lighting.confidence, 0.3)
    return {"lighting": asdict(lighting), "skin": asdict(skin)}


def analyze_outfit_photo(data: bytes | str) -> dict:
    img = decode_image(data)
    px, lighting = correct_lighting(img)
    colors = dominant_colors(center_crop(px, 0.6), k=6)
    key = [c for c in colors if c["share"] >= 0.06][:5] or colors[:3]
    return {"lighting": asdict(lighting), "colors": key,
            "harmony": harmony_report([c["hex"] for c in key])}

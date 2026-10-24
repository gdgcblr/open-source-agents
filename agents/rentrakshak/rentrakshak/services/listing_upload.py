"""Extract listing text from uploads: plain text, PDF, and images (vision)."""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import httpx

from rentrakshak.config import google_api_key, model_name
from rentrakshak.llm import ollama_api_base, ollama_model_tag, resolve_backend

VISION_PROMPT = (
    "Extract ALL readable text from this Bengaluru rental listing image "
    "(NoBroker, 99acres, MagicBricks, WhatsApp screenshot, etc.). "
    "Include rent, deposit, locality, BHK, furnishing, urgency phrases, and contact lines. "
    "Return plain text only — no markdown or commentary."
)

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_PDF_EXT = {".pdf"}


class ListingUploadError(Exception):
    pass


class VisionUnavailable(ListingUploadError):
    pass


def vision_backend() -> str:
    """mock | gemini | ollama | auto"""
    return os.environ.get("RENTRAKSHAK_VISION_BACKEND", "auto").strip().lower()


def _resolve_vision_backend() -> str:
    explicit = vision_backend()
    if explicit in ("mock", "gemini", "ollama", "none"):
        return explicit
    if explicit != "auto":
        raise ListingUploadError(f"Unknown RENTRAKSHAK_VISION_BACKEND: {explicit}")
    llm = resolve_backend()
    if llm == "ollama":
        return "ollama"
    if google_api_key():
        return "gemini"
    if _ollama_reachable():
        return "ollama"
    return "none"


def _ollama_reachable() -> bool:
    try:
        r = httpx.get(f"{ollama_api_base()}/api/tags", timeout=2.0)
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _mime_for_name(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".pdf"):
        return "application/pdf"
    return "image/jpeg"


def _validate_image(raw: bytes) -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ListingUploadError("Image support needs Pillow. pip install Pillow") from exc
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
    except Exception as exc:
        raise ListingUploadError("Invalid or corrupted image file") from exc
    # Re-open after verify for optional downscale
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    max_side = int(os.environ.get("RENTRAKSHAK_VISION_MAX_SIDE", "1600"))
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def _extract_pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ListingUploadError("PDF support needs pypdf. pip install pypdf") from exc
    reader = PdfReader(io.BytesIO(raw))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    return text


def _gemini_vision(image_bytes: bytes, mime: str) -> str:
    key = google_api_key()
    if not key:
        raise VisionUnavailable("GOOGLE_API_KEY not set")
    vision_model = os.environ.get("RENTRAKSHAK_VISION_MODEL", model_name())
    b64 = base64.b64encode(image_bytes).decode("ascii")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{vision_model}:generateContent?key={key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": VISION_PROMPT},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            }
        ]
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, json=payload)
    if r.status_code != 200:
        raise ListingUploadError(f"Gemini vision failed ({r.status_code}): {r.text[:300]}")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ListingUploadError("Gemini returned no text") from exc


def _ollama_vision(image_bytes: bytes) -> str:
    model = ollama_model_tag().split("/")[-1]
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": VISION_PROMPT, "images": [b64]}],
        "stream": False,
    }
    with httpx.Client(timeout=180.0) as client:
        r = client.post(f"{ollama_api_base()}/api/chat", json=payload)
    if r.status_code != 200:
        raise ListingUploadError(f"Ollama vision failed ({r.status_code}): {r.text[:300]}")
    data = r.json()
    msg = data.get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text:
        raise ListingUploadError("Ollama returned empty text — use a vision-capable model (e.g. gemma3:4b)")
    return text


def _run_vision(image_bytes: bytes, mime: str) -> tuple[str, str]:
    backend = _resolve_vision_backend()
    if backend == "mock":
        return os.environ.get("RENTRAKSHAK_MOCK_OCR_TEXT", "2 BHK Koramangala rent 28000 deposit 3 months"), "mock"
    if backend == "none":
        raise VisionUnavailable(
            "No vision backend. Set GOOGLE_API_KEY, run Ollama (gemma3:4b), or "
            "RENTRAKSHAK_VISION_BACKEND=ollama|gemini."
        )
    if backend == "gemini":
        return _gemini_vision(image_bytes, mime), "gemini"
    return _ollama_vision(image_bytes), "ollama"


def process_listing_upload(raw: bytes, filename: str) -> dict[str, Any]:
    """Return extracted_text, flags, optional preview and vision backend used."""
    name = filename or "upload"
    lower = name.lower()
    if len(raw) > 5_000_000:
        raise ListingUploadError("File too large (max 5MB)")

    if lower.endswith(".txt"):
        text = raw.decode("utf-8", errors="replace")
        return {
            "filename": name,
            "extracted_text": text,
            "ocr_applied": False,
            "content_type": "text/plain",
        }

    if any(lower.endswith(ext) for ext in _PDF_EXT):
        text = _extract_pdf_text(raw)
        if len(text) >= 40:
            return {
                "filename": name,
                "extracted_text": text,
                "ocr_applied": False,
                "content_type": "application/pdf",
            }
        return {
            "filename": name,
            "extracted_text": text,
            "ocr_applied": False,
            "content_type": "application/pdf",
            "message": (
                "This PDF has little selectable text. Upload a JPG/PNG screenshot of the listing "
                "for Gemma/Gemini vision OCR, or paste the description manually."
            ),
        }

    if any(lower.endswith(ext) for ext in _IMAGE_EXT):
        mime = _mime_for_name(name)
        image_bytes = _validate_image(raw)
        preview_b64 = base64.b64encode(image_bytes).decode("ascii")
        try:
            text, used = _run_vision(image_bytes, "image/jpeg")
        except VisionUnavailable as exc:
            return {
                "filename": name,
                "extracted_text": "",
                "ocr_applied": False,
                "content_type": mime,
                "preview_base64": preview_b64,
                "preview_mime": "image/jpeg",
                "message": str(exc),
            }
        except ListingUploadError:
            raise
        if len(text) < 15:
            raise ListingUploadError("Vision could not read enough text from this image — try a clearer screenshot.")
        return {
            "filename": name,
            "extracted_text": text,
            "ocr_applied": True,
            "content_type": mime,
            "vision_backend": used,
            "preview_base64": preview_b64,
            "preview_mime": "image/jpeg",
        }

    raise ListingUploadError("Unsupported file type. Use .txt, .jpg, .png, .webp, or .pdf")

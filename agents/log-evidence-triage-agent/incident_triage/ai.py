"""Optional AI boundary. Provider failures never replace deterministic evidence."""
import asyncio
from copy import deepcopy
import os

from .config import bounded_int
from .credibility import apply_candidate, citations_valid


class ProviderUnavailable(Exception):
    """Only allowlisted diagnostic categories cross the SDK boundary."""


def model_bundle(report: dict) -> dict:
    # No raw logs, arbitrary excerpts, filenames, metadata strings, or history.
    return {"decision": report["decision"], "claims": deepcopy(report["findings"])}


async def enhance(report: dict, responder=None) -> dict:
    result = deepcopy(report)
    result["mode"] = "offline_fallback"
    if not citations_valid(report):
        raise ValueError("Internal evidence validation failed")
    if not report["findings"]:
        result["fallback_reason"] = "No supported findings are available for AI selection."
        return result
    if responder is None:
        key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not key or key.upper() in {"YOUR_API_KEY_HERE", "REPLACE_ME", "PLACEHOLDER"}:
            result["fallback_reason"] = "GOOGLE_API_KEY is missing or a placeholder; configure it locally to enable Gemini."
            return result
        if not os.getenv("MODEL_NAME", "").strip():
            result["fallback_reason"] = "MODEL_NAME is missing; configure an available Gemini model."
            return result
        try:
            from .adk_adapter import select_findings
            responder = select_findings
        except ImportError:
            result["fallback_reason"] = "Optional ADK dependencies are unavailable; install requirements.txt for AI mode."
            return result
    try:
        timeout = bounded_int("TRIAGE_AI_TIMEOUT_SECONDS", 60, 120)
        candidate = await asyncio.wait_for(responder(model_bundle(report)), timeout=timeout)
        return apply_candidate(report, candidate)
    except ProviderUnavailable as exc:
        category = str(exc) if str(exc) in {"authentication", "quota", "model_or_endpoint", "provider_unavailable"} else "provider_unavailable"
        result["fallback_reason"] = f"AI {category} failure; deterministic non-AI findings retained. Check local Gemini configuration."
        return result
    except TimeoutError:
        result["fallback_reason"] = "AI timed out; deterministic non-AI findings retained."
        return result
    except Exception:
        # SDK exceptions may contain request URLs, credentials, or user data.
        result["fallback_reason"] = "AI unavailable, timed out, or configuration rejected; deterministic non-AI findings retained."
        return result

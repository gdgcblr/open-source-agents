from __future__ import annotations

import os
from typing import Any

from rentrakshak.config import google_api_key, model_name


def llm_backend() -> str:
    """gemini | ollama | auto"""
    return os.environ.get("RENTRAKSHAK_LLM_BACKEND", "auto").strip().lower()


def ollama_model_tag() -> str:
    return os.environ.get("RENTRAKSHAK_OLLAMA_MODEL", "gemma3:4b").strip()


def ollama_api_base() -> str:
    return os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434").strip().rstrip("/")


def resolve_backend() -> str:
    backend = llm_backend()
    if backend == "auto":
        if google_api_key():
            return "gemini"
        if os.environ.get("RENTRAKSHAK_USE_OLLAMA", "").lower() in ("1", "true", "yes"):
            return "ollama"
        return "gemini"
    if backend in ("gemini", "google"):
        return "gemini"
    if backend in ("ollama", "local", "gemma"):
        return "ollama"
    raise ValueError(f"Unknown RENTRAKSHAK_LLM_BACKEND: {backend}")


def resolve_agent_model() -> str | Any:
    """
    ADK Agent `model` argument: Gemini model id string, or LiteLlm for Ollama Gemma.

    Ollama requires: pip install 'google-adk[extensions]' (litellm) and a running Ollama daemon.
    """
    backend = resolve_backend()
    if backend == "ollama":
        try:
            from google.adk.models.lite_llm import LiteLlm
        except ImportError as exc:
            raise ImportError(
                "Local Gemma via Ollama needs LiteLLM. Install with: "
                "pip install 'google-adk[extensions]'"
            ) from exc
        tag = ollama_model_tag()
        litellm_id = tag if tag.startswith("ollama/") else f"ollama/{tag}"
        return LiteLlm(
            model=litellm_id,
            api_base=ollama_api_base(),
        )
    return model_name()


def model_description_for_docs() -> str:
    backend = resolve_backend()
    if backend == "ollama":
        return f"Ollama Gemma ({ollama_model_tag()}) @ {ollama_api_base()}"
    return f"Gemini ({model_name()})"

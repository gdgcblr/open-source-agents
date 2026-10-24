"""Model selection: Gemini (default) or any OpenAI-compatible endpoint such as NVIDIA."""

import logging
import os

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _quiet_litellm() -> None:
    """LiteLLM logs every model call at INFO; keep the console for the review itself."""
    import litellm

    litellm.suppress_debug_info = True
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_model():
    """Return the model for ``Agent(model=...)`` based on environment variables.

    MODEL_PROVIDER=gemini (default): MODEL_NAME is a Gemini model id; uses GOOGLE_API_KEY.
    MODEL_PROVIDER=nvidia: MODEL_NAME is the exact NVIDIA model id from build.nvidia.com;
        uses NVIDIA_API_KEY and NVIDIA_BASE_URL (optional).
    """
    provider = os.getenv("MODEL_PROVIDER", "gemini").strip().lower()
    name = os.getenv("MODEL_NAME", "").strip()

    if provider == "gemini":
        return name or DEFAULT_GEMINI_MODEL

    if provider == "nvidia":
        if not name:
            raise ValueError("MODEL_PROVIDER=nvidia requires MODEL_NAME (the exact NVIDIA model id).")
        api_key = os.getenv("NVIDIA_API_KEY", "").strip()
        if not api_key:
            raise ValueError("MODEL_PROVIDER=nvidia requires NVIDIA_API_KEY.")
        os.environ.setdefault("LITELLM_LOG", "ERROR")  # read when litellm is first imported
        try:
            from google.adk.models.lite_llm import LiteLlm
        except ImportError as exc:
            raise ImportError("NVIDIA mode needs extra packages: pip install -r requirements-nvidia.txt") from exc
        _quiet_litellm()
        return LiteLlm(
            model=f"openai/{name}",
            api_base=os.getenv("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL),
            api_key=api_key,
        )

    raise ValueError(f"Unknown MODEL_PROVIDER '{provider}'. Use 'gemini' or 'nvidia'.")

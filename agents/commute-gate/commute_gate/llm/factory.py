from __future__ import annotations

from commute_gate.config import Settings
from commute_gate.llm.none import NoneLLMProvider
from commute_gate.llm.ollama import OllamaProvider


def get_llm_provider(settings: Settings):
    if settings.llm_provider in {"none", "rules", "off"}:
        return NoneLLMProvider()
    if settings.llm_provider == "ollama":
        return OllamaProvider(settings.ollama_host, settings.ollama_model)
    raise ValueError(
        f"Unknown LLM_PROVIDER={settings.llm_provider!r}. Use 'ollama' or 'none'."
    )

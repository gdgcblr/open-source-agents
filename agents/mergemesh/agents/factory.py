"""ADK Agent factory configured for local-first execution via Ollama (Gemma).

Hosted external LLM providers are isolated and disabled in the default local-only runtime
so that no project data leaves the machine and no paid API credits are required.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

from agents.prompts import SYSTEM_PROMPT
from agents.tools import ADK_DETERMINISTIC_TOOLS
from config.settings import AppSettings, _is_loopback_url

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="google.adk")


@dataclass
class AgentDescriptor:
    mode: str
    provider_label: str
    model_id: str
    adk_agent: Any | None
    error_reason: str | None = None


def _normalize_ollama_messages(messages: Any) -> Any:
    """Convert ADK 'developer' role messages to 'system' so Ollama chat templates apply them."""
    if not isinstance(messages, list):
        return messages
    normalized = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "developer":
            copied = dict(msg)
            copied["role"] = "system"
            normalized.append(copied)
        else:
            normalized.append(msg)
    return normalized


def create_adk_agent(
    settings: AppSettings,
    stage: str = "primary",
    include_tools: bool = False,
) -> AgentDescriptor:
    """Create a Google ADK Agent configured for local Ollama inference (`ollama_chat/<model>`).

    By default (`include_tools=False`), the explainer agent receives pre-extracted deterministic
    evidence directly in its prompt and runs in structured JSON synthesis mode without attaching
    function-calling tools (avoiding Ollama HTTP 400 tool errors on Gemma 3 and preventing
    redundant tool invocations during synthesis).
    """
    effective_mode = settings.ai_mode
    if settings.ai_mode == "hybrid":
        effective_mode = "local" if stage == "extract" else "gemini"

    if effective_mode == "deterministic":
        return AgentDescriptor(
            mode="deterministic",
            provider_label="Deterministic Local Engine (No LLM)",
            model_id="deterministic",
            adk_agent=None,
            error_reason="Pure deterministic mode selected; LLM calls skipped by design.",
        )

    if effective_mode == "gemini":
        model_id = settings.gemini_model
        litellm_model = (
            model_id
            if "/" in model_id
            else (f"vertex_ai/{model_id}" if settings.gemini_backend == "vertex_ai" else f"gemini/{model_id}")
        )
        provider_label = (
            f"Hosted Gemma ({model_id} via ADK + Vertex AI)"
            if settings.gemini_backend == "vertex_ai"
            else f"Hosted Gemma ({model_id} via ADK + Google Gemini API)"
        )
        if not settings.is_gemini_configured():
            return AgentDescriptor(
                mode="gemini",
                provider_label="Hosted Gemma (Not Configured)",
                model_id=model_id,
                adk_agent=None,
                error_reason="Gemini credentials are not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY in .env.",
            )
        try:
            from google.adk.agents import Agent
            from google.adk.models.lite_llm import LiteLLMClient, LiteLlm

            class HostedGemmaLiteLLMClient(LiteLLMClient):
                """LiteLLM client wrapper that normalizes ADK developer roles for hosted Gemma."""

                async def acompletion(self, model: Any, messages: Any, tools: Any, **kwargs: Any) -> Any:
                    return await super().acompletion(
                        model=model,
                        messages=_normalize_ollama_messages(messages),
                        tools=tools,
                        **kwargs,
                    )

                def completion(self, model: Any, messages: Any, tools: Any, stream: bool = False, **kwargs: Any) -> Any:
                    return super().completion(
                        model=model,
                        messages=_normalize_ollama_messages(messages),
                        tools=tools,
                        stream=stream,
                        **kwargs,
                    )

            llm_kwargs: dict[str, Any] = {
                "temperature": 0.1,
                "max_tokens": max(settings.ai_max_output_tokens, 4096),
                "llm_client": HostedGemmaLiteLLMClient(),
            }
            api_key = settings.get_active_gemini_key()
            if api_key and settings.gemini_backend == "developer_api":
                llm_kwargs["api_key"] = api_key
            if not include_tools:
                llm_kwargs["response_format"] = {"type": "json_object"}

            llm_model = LiteLlm(model=litellm_model, **llm_kwargs)
            agent = Agent(
                name="mergemesh_hosted_gemma_explainer",
                model=llm_model,
                instruction=SYSTEM_PROMPT,
                description="Reasons over deterministic cross-repository compatibility evidence using hosted Gemma via Google Gemini API.",
                tools=ADK_DETERMINISTIC_TOOLS if include_tools else [],
            )
            return AgentDescriptor(
                mode="gemini",
                provider_label=provider_label,
                model_id=litellm_model,
                adk_agent=agent,
            )
        except Exception as exc:
            return AgentDescriptor(
                mode="gemini",
                provider_label=provider_label,
                model_id=litellm_model,
                adk_agent=None,
                error_reason=f"Failed to initialize hosted ADK LiteLlm model '{litellm_model}': {exc}",
            )

    model_tag = f"ollama_chat/{settings.ollama_model}"
    provider_label = f"Local Gemma ({settings.ollama_model} via ADK + Ollama)"

    if not _is_loopback_url(settings.ollama_base_url):
        return AgentDescriptor(
            mode="local",
            provider_label=provider_label,
            model_id=model_tag,
            adk_agent=None,
            error_reason=(
                f"Blocked non-local OLLAMA_BASE_URL ({settings.ollama_base_url}); "
                "MergeMesh enforces local-only inference."
            ),
        )

    try:
        from google.adk.agents import Agent
        from google.adk.models.lite_llm import LiteLLMClient, LiteLlm

        class OllamaLiteLLMClient(LiteLLMClient):
            """LiteLLM client wrapper that normalizes ADK developer roles for Ollama."""

            async def acompletion(self, model: Any, messages: Any, tools: Any, **kwargs: Any) -> Any:
                return await super().acompletion(
                    model=model,
                    messages=_normalize_ollama_messages(messages),
                    tools=tools,
                    **kwargs,
                )

            def completion(self, model: Any, messages: Any, tools: Any, stream: bool = False, **kwargs: Any) -> Any:
                return super().completion(
                    model=model,
                    messages=_normalize_ollama_messages(messages),
                    tools=tools,
                    stream=stream,
                    **kwargs,
                )

        llm_kwargs: dict[str, Any] = {
            "api_base": settings.ollama_base_url,
            "temperature": 0.1,
            "max_tokens": settings.ai_max_output_tokens,
            "llm_client": OllamaLiteLLMClient(),
        }
        if not include_tools:
            llm_kwargs["response_format"] = {"type": "json_object"}

        llm_model = LiteLlm(model=model_tag, **llm_kwargs)
        agent = Agent(
            name="mergemesh_local_gemma_explainer",
            model=llm_model,
            instruction=SYSTEM_PROMPT,
            description="Reasons over deterministic cross-repository compatibility evidence using local Gemma via Ollama.",
            tools=ADK_DETERMINISTIC_TOOLS if include_tools else [],
        )
        return AgentDescriptor(
            mode="local",
            provider_label=provider_label,
            model_id=model_tag,
            adk_agent=agent,
        )
    except Exception as exc:
        return AgentDescriptor(
            mode="local",
            provider_label=provider_label,
            model_id=model_tag,
            adk_agent=None,
            error_reason=f"Failed to initialize local ADK LiteLlm model '{model_tag}': {exc}",
        )

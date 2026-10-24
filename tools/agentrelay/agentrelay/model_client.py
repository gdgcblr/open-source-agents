"""Provider-agnostic model client abstraction with strict offline-first support."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from agentrelay.config import Config, get_config
from agentrelay.evidence import redact_secrets


class ModelError(RuntimeError):
    """Raised when model invocation fails."""


class ModelUnavailableError(ModelError):
    """Raised when model is requested in offline mode or credentials are absent."""


@dataclass
class ModelUsage:
    """Token usage tracking, distinguishing measured counts from estimates."""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    is_measured: bool = False
    estimated_cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelResponse:
    """Structured response from a model invocation."""

    content: str
    structured_data: Optional[Dict[str, Any]] = None
    model_name: str = "offline"
    latency_ms: float = 0.0
    usage: ModelUsage = ModelUsage()
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "structured_data": self.structured_data,
            "model_name": self.model_name,
            "latency_ms": round(self.latency_ms, 2),
            "usage": self.usage.to_dict(),
            "cached": self.cached,
        }


class BaseModelClient(ABC):
    """Abstract interface for model providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        expected_json_keys: Optional[list[str]] = None,
    ) -> ModelResponse:
        """Execute model request and return validated response."""
        pass


class OfflineModelClient(BaseModelClient):
    """Zero-dependency offline model client.

    Guarantees no outbound network calls, no secrets leakage, and explicit abstention.
    """

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        expected_json_keys: Optional[list[str]] = None,
    ) -> ModelResponse:
        raise ModelUnavailableError(
            "AgentRelay is running in offline mode. Semantic model calling is disabled. "
            "To enable, set AGENTRELAY_OFFLINE_MODE=false and provide a valid API key."
        )


class MockModelClient(BaseModelClient):
    """Deterministic in-memory mock client for testing semantic reasoning workflows."""

    def __init__(
        self,
        canned_response: Optional[str] = None,
        canned_json: Optional[Dict[str, Any]] = None,
        latency_ms: float = 12.5,
    ) -> None:
        self.canned_response = canned_response or "Mock semantic analysis completed."
        self.canned_json = canned_json
        self.latency_ms = latency_ms
        self.call_history: list[dict[str, Any]] = []

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        expected_json_keys: Optional[list[str]] = None,
    ) -> ModelResponse:
        sanitized_prompt = redact_secrets(prompt)
        self.call_history.append(
            {
                "prompt": sanitized_prompt,
                "system_instruction": system_instruction,
                "timestamp": time.time(),
            }
        )

        structured = self.canned_json
        content = self.canned_response
        if structured is not None and not self.canned_response:
            content = json.dumps(structured)

        # Approximate token count for mock testing (clearly marked is_measured=False)
        approx_tokens = len(prompt.split()) + len(content.split())
        usage = ModelUsage(
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(content.split()),
            total_tokens=approx_tokens,
            is_measured=False,
            estimated_cost_usd=None,
        )

        return ModelResponse(
            content=content,
            structured_data=structured,
            model_name="mock-gemini-test",
            latency_ms=self.latency_ms,
            usage=usage,
            cached=False,
        )


class GeminiRestClient(BaseModelClient):
    """HTTP client for Google Gemini API using Python standard library."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash", timeout: int = 15) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        expected_json_keys: Optional[list[str]] = None,
    ) -> ModelResponse:
        # Strict security: sanitize prompt before transmission
        sanitized_prompt = redact_secrets(prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": sanitized_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json" if expected_json_keys else "text/plain",
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start_t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed_ms = (time.time() - start_t) * 1000.0
                body = json.loads(resp.read().decode("utf-8"))

            candidates = body.get("candidates", [])
            if not candidates:
                raise ModelError("Gemini API returned no candidates.")

            text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")

            # Extract usage metadata
            usage_meta = body.get("usageMetadata", {})
            prompt_tokens = usage_meta.get("promptTokenCount")
            comp_tokens = usage_meta.get("candidatesTokenCount")
            total_tokens = usage_meta.get("totalTokenCount")

            usage = ModelUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=comp_tokens,
                total_tokens=total_tokens,
                is_measured=True,
                estimated_cost_usd=None,
            )

            structured = None
            if expected_json_keys:
                try:
                    structured = json.loads(text_content)
                except json.JSONDecodeError:
                    pass

            return ModelResponse(
                content=text_content,
                structured_data=structured,
                model_name=self.model_name,
                latency_ms=elapsed_ms,
                usage=usage,
                cached=False,
            )

        except urllib.error.HTTPError as exc:
            elapsed_ms = (time.time() - start_t) * 1000.0
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ModelError(f"Gemini API HTTP {exc.code} error: {error_body}") from exc
        except Exception as exc:
            elapsed_ms = (time.time() - start_t) * 1000.0
            raise ModelError(f"Gemini API request failed: {exc}") from exc


def get_model_client(config: Optional[Config] = None) -> BaseModelClient:
    """Factory to obtain the configured model client."""
    cfg = config or get_config()
    if cfg.offline_mode or cfg.model_provider == "offline":
        return OfflineModelClient()
    if cfg.model_provider == "gemini":
        if not cfg.gemini_api_key:
            return OfflineModelClient()
        return GeminiRestClient(
            api_key=cfg.gemini_api_key,
            model_name=cfg.model_name,
            timeout=cfg.request_timeout_seconds,
        )
    return OfflineModelClient()

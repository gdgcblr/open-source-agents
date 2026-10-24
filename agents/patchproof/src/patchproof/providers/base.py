"""LLMProvider protocol, budget-guarded invoker, and deterministic offline adapter."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

TModel = TypeVar("TModel", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised when an LLMProvider call fails, times out, or returns invalid schema."""


class ProviderBudgetExceededError(ProviderError):
    """Raised when a run exceeds the configured max_model_calls budget."""


class LLMProvider(Protocol):
    """Abstract interface for optional structured model generation."""

    @property
    def name(self) -> str:
        """Identifier for the provider."""
        ...

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        untrusted_context: dict[str, Any],
        response_schema: type[TModel],
    ) -> TModel:
        """Generate a validated Pydantic response object for the given role."""
        ...


class NullLLMProvider:
    """Offline no-op provider that signals deterministic mode is active."""

    @property
    def name(self) -> str:
        return "none"

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        untrusted_context: dict[str, Any],
        response_schema: type[TModel],
    ) -> TModel:
        raise ProviderError(
            f"Provider call requested for role '{role}', but NullLLMProvider is active"
        )


class DeterministicFakeLLMProvider:
    """Deterministic fake provider for testing provider-backed agent orchestration offline."""

    def __init__(
        self,
        responses: dict[str, BaseModel | dict[str, Any] | str | Callable[[dict[str, Any]], Any]]
        | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "fake_deterministic"

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        untrusted_context: dict[str, Any],
        response_schema: type[TModel],
    ) -> TModel:
        with self._lock:
            self.calls.append(
                {
                    "role": role,
                    "system_prompt": system_prompt,
                    "untrusted_context": untrusted_context,
                    "schema": response_schema.__name__,
                }
            )
        if role not in self._responses:
            raise ProviderError(f"No fake response configured for role '{role}'")
        entry = self._responses[role]
        raw = entry(untrusted_context) if callable(entry) else entry
        if isinstance(raw, response_schema):
            return validate_provider_payload(raw.model_dump(), response_schema)
        if isinstance(raw, BaseModel):
            return validate_provider_payload(raw.model_dump(), response_schema)
        return validate_provider_payload(raw, response_schema)


class BudgetedLLMProvider:
    """Thread-safe wrapper enforcing max_model_calls and bounded retries per agent call."""

    def __init__(
        self,
        delegate: LLMProvider,
        *,
        max_model_calls: int = 20,
        max_retries_per_agent: int = 1,
    ) -> None:
        self._delegate = delegate
        self._max_model_calls = max_model_calls
        self._max_retries_per_agent = max_retries_per_agent
        self._call_count = 0
        self._retry_count = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._delegate.name

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    @property
    def retry_count(self) -> int:
        with self._lock:
            return self._retry_count

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        untrusted_context: dict[str, Any],
        response_schema: type[TModel],
    ) -> TModel:
        last_error: Exception | None = None
        max_attempts = 1 + max(0, self._max_retries_per_agent)

        for attempt in range(1, max_attempts + 1):
            with self._lock:
                if self._call_count >= self._max_model_calls:
                    raise ProviderBudgetExceededError(
                        f"Model call budget exhausted (max_model_calls={self._max_model_calls}) "
                        f"before role '{role}' attempt {attempt}"
                    )
                self._call_count += 1
                if attempt > 1:
                    self._retry_count += 1

            try:
                raw_result = self._delegate.generate_structured(
                    role=role,
                    system_prompt=system_prompt,
                    untrusted_context=untrusted_context,
                    response_schema=response_schema,
                )
                if isinstance(raw_result, BaseModel):
                    return validate_provider_payload(raw_result.model_dump(), response_schema)
                return validate_provider_payload(raw_result, response_schema)
            except ProviderBudgetExceededError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break

        raise ProviderError(
            f"Provider '{self._delegate.name}' failed for role '{role}' after "
            f"{max_attempts} attempt(s): {last_error}"
        ) from last_error


def validate_provider_payload(
    raw_payload: dict[str, Any] | str,
    schema: type[TModel],
) -> TModel:
    """Validate raw provider output against a typed Pydantic schema or raise ProviderError."""
    try:
        if isinstance(raw_payload, str):
            return schema.model_validate_json(raw_payload)
        return schema.model_validate(raw_payload)
    except ValidationError as exc:
        raise ProviderError(f"Malformed provider output for {schema.__name__}: {exc}") from exc



"""Gateways: the only module that knows model providers exist.

Everything above this speaks in terms of "a worker with an id, a model string
and a credential". Three implementations of one method:

* ``MockGateway``: deterministic and offline. The whole engine runs for real;
  only the model call is simulated.
* ``HTTPGateway``: OpenAI-compatible ``/chat/completions`` over the standard
  library. The default for live calls.
* ``LiteLLMGateway``: optional, for LiteLLM's wider provider coverage
  (``COE_GATEWAY=litellm``, needs ``pip install litellm``).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Callable, Protocol

from context_orchestration.contracts import WorkerConfig
from context_orchestration.demo import mock_claims

USER_AGENT = "context-orchestration-engine/0.1"

# "<provider>/<model id>" picks the endpoint. An explicit api_base wins.
PROVIDER_BASES = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com/v1",
    "ollama": "http://localhost:11434/v1",
}

RETRYABLE = {429, 500, 502, 503, 504}


class GatewayError(RuntimeError):
    pass


class Gateway(Protocol):
    def complete(self, config: WorkerConfig, messages: list[dict]) -> str: ...


def split_model(model: str) -> tuple[str | None, str]:
    provider, _, rest = model.partition("/")
    if rest and provider in PROVIDER_BASES:
        return provider, rest
    return None, model


class MockGateway:
    """Answers from the demo script, keyed by the assigned task in the briefing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict]]] = []

    def complete(self, config: WorkerConfig, messages: list[dict]) -> str:
        self.calls.append((config.id, [dict(m) for m in messages]))
        match = re.search(r"YOUR ASSIGNED TASK\n- (.+)", messages[-1]["content"])
        task = match.group(1).strip() if match else "the assigned task"
        return json.dumps(mock_claims(task))


class HTTPGateway:
    def __init__(self, timeout: float = 120.0, sleep: Callable[[float], None] = time.sleep) -> None:
        self.timeout = timeout
        self.sleep = sleep

    def complete(self, config: WorkerConfig, messages: list[dict]) -> str:
        provider, model_id = split_model(config.model)
        base = config.api_base or PROVIDER_BASES.get(provider or "")
        if not base:
            raise GatewayError(
                f"{config.id}: no endpoint for model {config.model!r}. Prefix it with one of "
                f"{', '.join(PROVIDER_BASES)} or set api_base in workers.json."
            )
        url = base.rstrip("/") + "/chat/completions"
        body = json.dumps({
            "model": model_id,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        key = config.resolve_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"

        for attempt in range(config.max_retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE and attempt < config.max_retries:
                    self.sleep(_retry_delay(exc, attempt))
                    continue
                detail = exc.read().decode("utf-8", "replace")[:300]
                raise GatewayError(f"{config.id}: HTTP {exc.code} from {base}: {detail}") from None
            except urllib.error.URLError as exc:
                if attempt < config.max_retries:
                    self.sleep(min(2 ** attempt, 30))
                    continue
                raise GatewayError(f"{config.id}: cannot reach {base}: {exc.reason}") from None
            except (KeyError, IndexError, ValueError) as exc:
                raise GatewayError(f"{config.id}: unexpected response shape from {base}") from exc
        raise GatewayError(f"{config.id}: retries exhausted")  # pragma: no cover


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    header = exc.headers.get("retry-after") if exc.headers else None
    try:
        return min(float(header), 60.0)
    except (TypeError, ValueError):
        return float(min(2 ** attempt, 30))


class LiteLLMGateway:
    def complete(self, config: WorkerConfig, messages: list[dict]) -> str:
        try:
            import litellm  # optional dependency
        except ImportError as exc:
            raise GatewayError(
                "COE_GATEWAY=litellm needs LiteLLM: pip install litellm"
            ) from exc
        response = litellm.completion(
            model=config.model,
            messages=messages,
            api_key=config.resolve_key(),
            api_base=config.api_base,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            num_retries=config.max_retries,
        )
        return response.choices[0].message.content or ""


def build_gateway(mock: bool) -> Gateway:
    if mock:
        return MockGateway()
    if os.environ.get("COE_GATEWAY", "").strip().lower() == "litellm":
        return LiteLLMGateway()
    return HTTPGateway()

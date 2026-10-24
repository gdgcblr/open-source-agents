"""Optional model providers for end-to-end evaluation.

Providers are plain HTTPS clients (standard library only) behind one small
interface, so no vendor SDK is required. They are only constructed when you
run ``prompt-enhancer eval-e2e`` with ``--provider``; the rest of the toolkit
never sends prompts anywhere. API keys come from environment variables and are
never logged. Prompt contents are not logged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from collections.abc import Callable

Transport = Callable[[str, dict[str, str], bytes, float], dict]


@dataclass
class Completion:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    ms: float


class Provider(Protocol):
    name: str

    def complete(self, prompt: str, model: str, max_tokens: int = 1024) -> Completion: ...


class ProviderError(RuntimeError):
    pass


def https_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict:
    if not url.startswith("https://"):
        raise ProviderError("refusing non-https provider URL")
    req = urllib.request.Request(url, data=body, headers={**headers, "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https enforced above
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # include the status and the provider's error type, never the request body
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ProviderError(f"HTTP {e.code} from provider: {detail}") from None


def _key(var: str) -> str:
    v = os.environ.get(var, "").strip()
    if not v:
        raise ProviderError(f"set {var} to use this provider (see .env.example)")
    return v


class _HTTPProvider:
    name = "base"
    key_env = ""

    def __init__(self, transport: Transport | None = None, timeout: float = 120.0, api_key: str | None = None):
        self.transport = transport or https_transport
        self.timeout = timeout
        self.api_key = api_key or _key(self.key_env)

    def _call(self, url: str, headers: dict[str, str], payload: dict) -> tuple[dict, float]:
        t0 = time.perf_counter()
        data = self.transport(url, headers, json.dumps(payload).encode("utf-8"), self.timeout)
        return data, (time.perf_counter() - t0) * 1000


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"
    key_env = "ANTHROPIC_API_KEY"

    def complete(self, prompt: str, model: str, max_tokens: int = 1024) -> Completion:
        data, ms = self._call(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
        )
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        u = data.get("usage", {})
        return Completion(text, u.get("input_tokens"), u.get("output_tokens"), ms)


class OpenAIProvider(_HTTPProvider):
    name = "openai"
    key_env = "OPENAI_API_KEY"

    def complete(self, prompt: str, model: str, max_tokens: int = 1024) -> Completion:
        data, ms = self._call(
            "https://api.openai.com/v1/chat/completions",
            {"authorization": f"Bearer {self.api_key}"},
            {"model": model, "messages": [{"role": "user", "content": prompt}], "max_completion_tokens": max_tokens},
        )
        choice = (data.get("choices") or [{}])[0]
        u = data.get("usage", {})
        return Completion(choice.get("message", {}).get("content") or "", u.get("prompt_tokens"), u.get("completion_tokens"), ms)


class GeminiProvider(_HTTPProvider):
    name = "gemini"
    key_env = "GEMINI_API_KEY"

    def complete(self, prompt: str, model: str, max_tokens: int = 1024) -> Completion:
        data, ms = self._call(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": self.api_key},  # header, never in the URL
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}},
        )
        cand = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        u = data.get("usageMetadata", {})
        return Completion(text, u.get("promptTokenCount"), u.get("candidatesTokenCount"), ms)


class ClaudeCodeProvider:
    """Runs prompts through the Claude Code CLI (``claude -p``) using the user's existing Claude login.

    No API key is needed. Each call is isolated so nothing but the prompt reaches
    the model: ``--safe-mode`` (no CLAUDE.md, plugins, hooks, MCP servers or
    skills), ``--tools ""`` (no tools), a short neutral system prompt, an empty
    temporary working directory, and no saved session. Uses your plan's usage.
    """

    name = "claude-code"
    SYSTEM = "You are a helpful assistant. Answer the user's request directly."

    def __init__(self, binary: str | None = None, timeout: float = 300.0, runner: Callable[..., subprocess.CompletedProcess] | None = None):
        found = binary or os.environ.get("PROMPT_ENHANCER_CLAUDE_BIN") or shutil.which("claude")
        if not found:
            raise ProviderError("Claude Code CLI not found; put `claude` on PATH or set PROMPT_ENHANCER_CLAUDE_BIN")
        self.binary: str = found
        self.timeout = timeout
        self.runner = runner or subprocess.run
        self.cwd = tempfile.mkdtemp(prefix="prompt-enhancer-e2e-")

    def args(self, model: str) -> list[str]:
        return [self.binary, "-p", "--model", model, "--safe-mode", "--tools", "", "--no-session-persistence",
                "--system-prompt", self.SYSTEM, "--output-format", "json"]

    def complete(self, prompt: str, model: str, max_tokens: int = 1024) -> Completion:
        t0 = time.perf_counter()
        proc = self.runner(self.args(model), input=prompt, capture_output=True, text=True, timeout=self.timeout, cwd=self.cwd)
        ms = (time.perf_counter() - t0) * 1000
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            raise ProviderError(f"claude -p exited {proc.returncode} without JSON output") from None
        if data.get("is_error") or proc.returncode != 0:
            raise ProviderError(f"claude -p reported an error (subtype {data.get('subtype')!r})")
        u = data.get("usage", {})
        return Completion(str(data.get("result", "")), u.get("input_tokens"), u.get("output_tokens"), ms)


class MockProvider:
    """Deterministic provider for tests and dry runs. Results are labelled as mock in every report."""

    name = "mock"

    def __init__(self, respond: Callable[[str, str], str] | None = None):
        self.respond = respond or (lambda prompt, model: prompt[:200])

    def complete(self, prompt: str, model: str, max_tokens: int = 1024) -> Completion:
        return Completion(self.respond(prompt, model), None, None, 0.0)


PROVIDERS: dict[str, type] = {
    "claude-code": ClaudeCodeProvider, "anthropic": AnthropicProvider, "openai": OpenAIProvider, "gemini": GeminiProvider, "mock": MockProvider,
}


def get_provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise ProviderError(f"unknown provider {name!r}; choose from {', '.join(PROVIDERS)}")
    return PROVIDERS[name]()

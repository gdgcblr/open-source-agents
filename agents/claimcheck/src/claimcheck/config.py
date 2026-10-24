from __future__ import annotations

import os
from dataclasses import dataclass

from claimcheck.safety import validate_url

DEFAULT_MODEL = "hf.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL"


@dataclass(frozen=True)
class Settings:
    base_url: str = "http://localhost:11434"
    model: str = DEFAULT_MODEL
    allow_remote: bool = False
    allow_http: bool = False
    timeout: float = 180
    max_calls: int = 8

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            base_url=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", DEFAULT_MODEL),
            allow_remote=os.getenv("CLAIMCHECK_ALLOW_REMOTE_MODEL") == "1",
            allow_http=os.getenv("CLAIMCHECK_ALLOW_HTTP_MODEL") == "1",
        )
        return settings.validate()

    def validate(self) -> Settings:
        validate_url(self.base_url, allow_remote=self.allow_remote, allow_http=self.allow_http)
        if not self.model.strip() or not 1 <= self.max_calls <= 20 or self.timeout <= 0:
            raise ValueError("Model, timeout, or model-call budget is invalid")
        return self

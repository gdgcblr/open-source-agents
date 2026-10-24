from __future__ import annotations


class NoneLLMProvider:
    name = "none"
    model = "rules"

    def generate_json(self, prompt: str) -> dict:
        raise RuntimeError("Rule-only provider does not generate JSON.")

    def generate_text(self, prompt: str) -> str:
        raise RuntimeError("Rule-only provider does not generate text.")

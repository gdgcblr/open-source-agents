"""Conservative token/cost accounting to bound runaway usage."""
from dataclasses import dataclass


@dataclass
class CostMeter:
    max_cost_usd: float
    input_rate_per_million: float
    output_rate_per_million: float
    input_tokens: int = 0
    output_tokens: int = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Rough safety estimate only; not a tokenizer and not billing-grade.
        return max(1, (len(text) + 3) // 4)

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens * self.input_rate_per_million
            + self.output_tokens * self.output_rate_per_million
        ) / 1_000_000

    def record(self, input_text: str, output_text: str) -> None:
        self.input_tokens += self.estimate_tokens(input_text)
        self.output_tokens += self.estimate_tokens(output_text)

    def ensure_budget(self) -> None:
        if self.estimated_cost_usd >= self.max_cost_usd:
            raise RuntimeError("Estimated session cost budget reached; stopping safely.")

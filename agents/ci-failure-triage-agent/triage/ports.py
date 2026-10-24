"""Ports: interfaces the use-case depends on. Adapters implement them."""
from typing import Protocol

from .models import TestFailure, Verdict


class Provider(Protocol):
    def classify(self, failure: TestFailure, log_context: list[str]) -> Verdict: ...

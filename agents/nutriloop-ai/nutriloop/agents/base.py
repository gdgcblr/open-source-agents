"""
Base Agent Interface and LLM Provider Abstraction.
Supports standalone local deterministic execution (zero API key needed for reproducibility)
as well as optional live API integrations (e.g. Gemini / OpenAI).
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from nutriloop.models import AgentActionTrace

logger = logging.getLogger("nutriloop.agent")


class BaseAgent:
    """Foundational agent class supporting trace generation and LLM/deterministic fallback."""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.traces: List[AgentActionTrace] = []
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
        self.model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")

    def record_trace(self, action: str, reasoning: str, details: Optional[Dict[str, Any]] = None) -> AgentActionTrace:
        """Log an inspectable agent reasoning step."""
        trace = AgentActionTrace(
            agent_name=self.name,
            action=action,
            reasoning=reasoning,
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            details=details or {}
        )
        self.traces.append(trace)
        logger.info(f"[{self.name}] {action}: {reasoning}")
        return trace

    def clear_traces(self):
        """Reset internal traces before a new execution pass."""
        self.traces.clear()

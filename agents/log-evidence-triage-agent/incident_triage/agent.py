"""ADK entry point emitting only validated reports, including on API failure."""
import json

from dotenv import load_dotenv
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types

from .ai import enhance
from .config import PROJECT_ROOT
from .engine import MAX_BYTES
from .tools import investigate_request

load_dotenv(PROJECT_ROOT / ".env")


class TraceGuardAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        try:
            # Use only this invocation, never a previous session's ledger.
            message = "".join(p.text or "" for p in ctx.user_content.parts or [])
            if len(message.encode("utf-8")) > MAX_BYTES + 10_000:
                raise ValueError("Input exceeds the size limit")
            request = json.loads(message) if message.lstrip().startswith("{") else {"log_text": message}
            report = investigate_request(request)
            report = await enhance(report)
        except (ValueError, TypeError, OSError, UnicodeError):
            report = {"decision": "HOLD", "mode": "offline_deterministic",
                      "error": "Invalid request or unreadable file. Provide JSON with log_text or approved filename, product, exact version, and boolean exposure flags. Limits: UTF-8, 1 MB, 5000 lines."}
        yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=json.dumps(report))]))


root_agent = TraceGuardAgent(name="traceguard_ai", description="Evidence-driven PHP/Node.js investigation with deterministic human escalation.")

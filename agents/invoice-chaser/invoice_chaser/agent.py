"""ADK agents for Invoice Chaser.

root_agent (chat with the owner)
├── payment_matcher  (single-turn sub-agent, exposed to root as a tool)
└── reminder_drafter (single-turn sub-agent, exposed to root as a tool)

Each agent connects to the ledger MCP server with its own tool allow-list.
"""

import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

from invoice_chaser import prompts

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gemini-3.5-flash"

ROOT_TOOLS = ["get_chase_list", "list_open_invoices", "get_invoice", "list_pending_matches",
              "list_reminders", "run_report", "get_audit_log"]
MATCHER_TOOLS = ["list_unmatched_payments", "list_open_invoices", "propose_match"]
DRAFTER_TOOLS = ["get_chase_list", "get_client_context", "check_policy", "render_reminder",
                 "queue_reminder"]

ALLOWED_TOOLS = {
    "invoice_chaser": set(ROOT_TOOLS),
    "payment_matcher": set(MATCHER_TOOLS),
    "reminder_drafter": set(DRAFTER_TOOLS),
}
LEDGER_TOOLS = set().union(*ALLOWED_TOOLS.values())
RUN_SCOPED_TOOLS = {"propose_match", "queue_reminder", "run_report"}


def _ledger_toolset(tool_filter: list[str]) -> McpToolset:
    # Only ledger settings are passed to the tool process; API keys stay in this process.
    env = {k: v for k, v in os.environ.items() if k.startswith("INVOICE_CHASER_")}
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable, args=["-m", "ledger.mcp_server"],
                cwd=str(PROJECT_DIR), env=env),
            timeout=30.0),
        tool_filter=tool_filter,
    )


def start_run(callback_context):
    """Each owner request is one run; every write in it is tagged with this id."""
    callback_context.state["run_id"] = f"run-{uuid.uuid4().hex[:8]}"
    return None


def guard_tool_call(tool, args, tool_context):
    """Defence in depth on top of each toolset's tool_filter.

    - Blocks ledger tools outside the calling agent's allow-list.
    - Overwrites run_id so the model cannot choose or omit it.
    """
    if tool.name in LEDGER_TOOLS and tool.name not in ALLOWED_TOOLS.get(tool_context.agent_name, set()):
        return {"ok": False, "error_code": "TOOL_NOT_ALLOWED",
                "message": f"{tool_context.agent_name} may not call {tool.name}"}
    if tool.name in RUN_SCOPED_TOOLS:
        args["run_id"] = tool_context.state.get("run_id")
    return None


def _config(temperature: float) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(temperature=temperature)


def _static(text: str):
    # A callable instruction is used verbatim (no {state} substitution), so the
    # reminder slot names in the prompts stay literal.
    return lambda _ctx: text


# Server errors are retried by the client. Rate limits (429) are handled by QuotaAwareGemini,
# which can tell a per-minute limit (wait and retry) from a per-day one (stop and say so).
RETRY = types.HttpRetryOptions(attempts=4, initial_delay=5, max_delay=30, exp_base=2, jitter=2,
                               http_status_codes=[500, 502, 503, 504])
MAX_RATE_LIMIT_WAITS = 5

DAILY_QUOTA_MESSAGE = (
    "⚠ Gemini's daily free-tier quota for this API key is used up{reset}. Nothing was changed "
    "in the ledger by this step. For a demo without quota, run `python cli.py chase --replay`; "
    "otherwise use a key with more quota (set GOOGLE_API_KEY in .env).")


def _error_chain_text(error: BaseException) -> str:
    parts, seen, e = [], set(), error
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        parts.append(str(e))
        e = e.__cause__ or e.__context__
    return "\n".join(parts)


def classify_rate_limit(error: BaseException) -> tuple[str | None, float | None]:
    """('daily' | 'minute' | None, suggested wait in seconds)."""
    text = _error_chain_text(error)
    if "RESOURCE_EXHAUSTED" not in text and "429" not in text:
        return None, None
    if "PerDay" in text or "per day" in text.lower():
        return "daily", None
    m = re.search(r"retry in ([\d.]+)s", text) or re.search(r"retryDelay'?: '(\d+)s", text)
    return "minute", float(m[1]) if m else 20.0


def _reset_hint(error: BaseException) -> str:
    m = re.search(r"retry in (\d+h\d+m)", _error_chain_text(error))
    return f" (it resets in about {m[1].replace('h', 'h ')})" if m else ""


class QuotaAwareGemini(Gemini):
    """Gemini that waits out per-minute rate limits and fails fast, with a clear message
    shown to the user, when the daily quota is exhausted (instead of retrying for minutes)."""

    async def generate_content_async(self, llm_request, stream: bool = False):
        for attempt in range(MAX_RATE_LIMIT_WAITS + 1):
            yielded = False
            try:
                async for response in super().generate_content_async(llm_request, stream):
                    yielded = True
                    yield response
                return
            except Exception as e:
                kind, wait = classify_rate_limit(e)
                if kind == "daily" and not yielded:
                    yield LlmResponse(
                        content=types.Content(role="model", parts=[types.Part.from_text(
                            text=DAILY_QUOTA_MESSAGE.format(reset=_reset_hint(e)))]),
                        error_code="DAILY_QUOTA_EXHAUSTED")
                    return
                if kind == "minute" and not yielded and attempt < MAX_RATE_LIMIT_WAITS:
                    await asyncio.sleep(min(wait + 1, 65))
                    continue
                raise


def _model(model: str | BaseLlm | None) -> BaseLlm:
    if isinstance(model, BaseLlm):
        return model
    return QuotaAwareGemini(model=model or os.getenv("MODEL_NAME") or DEFAULT_MODEL, retry_options=RETRY)


def build_matcher(model: str | BaseLlm | None = None, mode: str | None = "single_turn") -> LlmAgent:
    return LlmAgent(
        name="payment_matcher",
        model=_model(model),
        mode=mode,
        description=prompts.MATCHER_DESCRIPTION,
        instruction=_static(prompts.MATCHER_INSTRUCTION),
        tools=[_ledger_toolset(MATCHER_TOOLS)],
        generate_content_config=_config(0.0),
        before_agent_callback=start_run if mode is None else None,
        before_tool_callback=guard_tool_call,
    )


def build_drafter(model: str | BaseLlm | None = None, mode: str | None = "single_turn") -> LlmAgent:
    return LlmAgent(
        name="reminder_drafter",
        model=_model(model),
        mode=mode,
        description=prompts.DRAFTER_DESCRIPTION,
        instruction=_static(prompts.DRAFTER_INSTRUCTION),
        tools=[_ledger_toolset(DRAFTER_TOOLS)],
        generate_content_config=_config(0.4),
        before_agent_callback=start_run if mode is None else None,
        before_tool_callback=guard_tool_call,
    )


def build_root_agent(model: str | BaseLlm | None = None,
                     matcher_model: str | BaseLlm | None = None,
                     drafter_model: str | BaseLlm | None = None) -> LlmAgent:
    """`mode=None` sub-agent builders are for evaluating one agent on its own."""
    return LlmAgent(
        name="invoice_chaser",
        model=_model(model),
        description="Helps a freelancer reconcile payments and chase overdue invoices.",
        instruction=_static(prompts.ROOT_INSTRUCTION),
        tools=[_ledger_toolset(ROOT_TOOLS)],
        sub_agents=[build_matcher(matcher_model or model), build_drafter(drafter_model or model)],
        generate_content_config=_config(0.2),
        before_agent_callback=start_run,
        before_tool_callback=guard_tool_call,
    )


root_agent = build_root_agent()

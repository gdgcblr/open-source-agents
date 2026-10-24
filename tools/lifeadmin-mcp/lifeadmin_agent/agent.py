"""Google ADK agent backed by a local Ollama Gemma model and LifeAdmin MCP tools."""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.models import LlmResponse
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("OLLAMA_API_BASE", "http://localhost:11434")

AGENT_INSTRUCTIONS = """
You are LifeAdmin, a careful personal deadline assistant. Use the MCP tools to
read and change reminders; never claim a reminder was saved or changed unless
the relevant tool succeeded. Interpret a yearless date as its next occurrence
after the current local date supplied below. Never guess a year from memory.
If a date is vague, could mean more than one day, or lacks necessary details,
ask a concise clarifying question before writing. Confirm the exact date and
time returned by the tool. Never invent due times.
Never call add_reminder unless both a clear task and a specific due_date are
known. A missing date means ask the user and make no tool call; do not try an
incomplete add_reminder call.

Use list_reminders to answer questions about saved tasks. When a user clearly
identifies one reminder by its title, pass that phrase as match_title to
update_reminder or mark_completed. The server acts only if exactly one
reminder matches. Use find_reminders when a title is not sufficiently specific.
If no reminder matches or several match, do not mutate anything; ask which
reminder the user means. Do not ask for an exact title or ID when the user's
description is sufficient to search. Only update or complete when asked.
Use the provided tools rather than explaining the tool workflow to the user.
Keep the user-facing response concise. Do not expose internal reasoning.
""".strip()


def _instructions_with_local_date() -> str:
    now = datetime.now().astimezone()
    local_date = now.strftime("%A, %Y-%m-%d")
    timezone = now.strftime("%Z %z").strip()
    return (
        f"{AGENT_INSTRUCTIONS}\n\n"
        f"Current local date: {local_date}. Local timezone: {timezone}."
    )


def _hide_model_thoughts(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse:
    if llm_response.content and llm_response.content.parts:
        llm_response.content.parts = [
            part
            for part in llm_response.content.parts
            if not getattr(part, "thought", False) or getattr(part, "function_call", None)
        ]
    return llm_response


def create_agent() -> LlmAgent:
    """Create an agent with a fresh MCP connection for a runner or evaluation."""
    return LlmAgent(
        model=LiteLlm(
            model=f"ollama_chat/{os.getenv('LIFEADMIN_MODEL', 'gemma4:e4b')}",
            extra_body={"think": True},
        ),
        name="lifeadmin_assistant",
        description="A local-first assistant for personal deadlines and reminders.",
        instruction=_instructions_with_local_date(),
        after_model_callback=_hide_model_thoughts,
        tools=[
            McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "lifeadmin_mcp.server"],
                        env=os.environ.copy(),
                    ),
                ),
            ),
        ],
    )


root_agent = create_agent()

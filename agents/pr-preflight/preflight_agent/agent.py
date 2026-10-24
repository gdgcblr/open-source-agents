import os

from google.adk.agents import Agent

from .guardrails import after_tool_callback, before_tool_callback
from .prompts import INSTRUCTION
from .tools import list_files, read_file, run_command

root_agent = Agent(
    name="preflight_agent",
    model=os.getenv("PREFLIGHT_MODEL", "gemini-3.8-flash"),
    instruction=INSTRUCTION,
    tools=[list_files, read_file, run_command],
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

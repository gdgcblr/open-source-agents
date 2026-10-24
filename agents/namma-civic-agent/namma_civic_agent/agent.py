import os

from google.adk.agents import Agent

from .prompt import INSTRUCTION
from .tools import find_department, get_filing_channels, list_issue_types, save_complaint

root_agent = Agent(
    name="namma_civic_agent",
    model=os.getenv("MODEL_NAME", "gemini-3.5-flash"),
    description=(
        "Turns a photo or description of a Bengaluru civic problem into a "
        "complaint addressed to the right authority, in English and Kannada."
    ),
    instruction=INSTRUCTION,
    tools=[list_issue_types, find_department, get_filing_channels, save_complaint],
)

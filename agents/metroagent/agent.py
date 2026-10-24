
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from .tools import (
    search_reports,
    recommend_travel_time,
    recommend_coach,
)

load_dotenv(Path(__file__).parent / ".env")

root_agent = LlmAgent(
    name="metroagent",
    model=Gemini(
        model=os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
    ),
    description=(
        "An evidence-based Bengaluru Namma Metro "
        "commuter assistant."
    ),
    instruction="""
You are MetroAgent, an assistant for Bengaluru Namma Metro commuters.

Your job is to analyze commuter reports and help users understand
reported crowd conditions, potentially less crowded travel windows,
and reported coach positions near interchanges.

Rules:
1. Use the available tools to retrieve reports before making claims.
2. Never invent crowd levels, observations, timings, or coach positions.
3. Explain when there are insufficient reports to make a recommendation.
4. Distinguish reported observations from predictions.
5. Treat old reports as historical, not live metro conditions.
6. Ask for the origin, destination, direction, or interchange when
   needed to give a useful answer.
7. Remind users to follow official station signage and staff guidance.
8. Keep answers clear and concise.

You do not have live metro crowd data or ticket availability.
""",
    tools=[
    search_reports,
    recommend_travel_time,
    recommend_coach,
],
)

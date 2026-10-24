"""
adk_agent.py - Google Agent Development Kit (ADK) Core Agent Setup
"""
import os
import json
from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from rag_tool import search_paper_context
from schemas import ResearchPaperArtifacts

ADK_INSTRUCTION = """You are a Principal AI Systems Research Scientist and Technical Lead.
Your objective is to deconstruct research papers and whitepapers into rigorous, structured artifacts.

You have access to the tool `search_paper_context`:
- Call `search_paper_context` to look up the core architecture and methodology.
- Call `search_paper_context` to find experimental evaluation tables and benchmark comparisons.
- Call `search_paper_context` to discover hardware constraints, tradeoffs, and failure modes.

When you have collected sufficient technical evidence from the tools, generate the final deconstruction report.
You MUST output your response strictly as a JSON object matching this schema:
{
  "title": "string",
  "authors": "string or null",
  "executive_summary": "string",
  "key_insights": ["string", "string", ...],
  "limitations_and_tradeoffs": ["string", "string", ...],
  "comparative_table": {
    "title": "string",
    "headers": ["col1", "col2", ...],
    "rows": [["val1", "val2"], ...]
  },
  "diagram_mermaid": "flowchart TD\\n  A[Start] --> B[Output]"
}

Do NOT wrap the JSON in extra commentary. Ensure the Mermaid code is syntactically correct.
"""

def build_scholar_adk_agent(model_name: str = "gemini-2.5-flash") -> Agent:
    """Builds an ADK Agent armed with RAG retrieval tools."""
    return Agent(
        name="scholar_paper_agent",
        model=model_name,
        instruction=ADK_INSTRUCTION,
        tools=[search_paper_context],
    )

class ADKScholarRunner:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.agent = build_scholar_adk_agent(model_name=model_name)
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=self.agent,
            app_name="ScholarLens",
            session_service=self.session_service
        )

    async def analyze(self, paper_source: str) -> ResearchPaperArtifacts:
        user_id = "user_terminal"
        session_id = "session_analysis"

        # FIX: Explicitly create the session first before invoking run_async
        await self.session_service.create_session(
            session_id=session_id,
            user_id=user_id,
            app_name="ScholarLens"
        )

        prompt_text = (
            f"Please analyze the newly ingested paper from '{paper_source}'. "
            "Use the `search_paper_context` tool to retrieve the methodology, benchmarks, "
            "and architecture details, then produce the final structured JSON artifacts."
        )

        user_content = Content(
            role="user",
            parts=[Part.from_text(text=prompt_text)]
        )

        response_chunks = []
        async for event in self.runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content
        ):
            if hasattr(event, "text") and event.text:
                response_chunks.append(event.text)
            elif hasattr(event, "content") and event.content:
                if hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            response_chunks.append(part.text)
                else:
                    response_chunks.append(str(event.content))

        full_output = "".join(response_chunks).strip()

        # Clean markdown code fences if wrapped
        if "```json" in full_output:
            full_output = full_output.split("```json")[1].split("```")[0].strip()
        elif "```" in full_output:
            full_output = full_output.split("```")[1].split("```")[0].strip()

        parsed_data = json.loads(full_output)
        return ResearchPaperArtifacts(**parsed_data)
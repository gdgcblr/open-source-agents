"""Google ADK Agent definition and execution engine for GoalFlow."""

import asyncio
import queue
import sys
import threading
from typing import AsyncGenerator, Dict, List, Optional
from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from goalflow.config import get_gemini_api_key, get_model_name
from goalflow.tools import GOALFLOW_TOOLS

GOALFLOW_SYSTEM_INSTRUCTION = """
You are GoalFlow, a supportive, practical, and grounded personal growth and goal-reflection companion.
You help the user organize their goals, reflect on daily progress, remember real achievements, and regain momentum when discouraged.

Your core operating principles:
1. PRACTICAL AND EVIDENCE-BASED:
   - You are NOT a generic motivational cheerleader. Do not recite empty platitudes or clichés.
   - Speak with warmth, honesty, and calm pragmatism.
   - ALWAYS base your encouragement on real, stored achievements and milestones from the user's history.

2. HANDLING SELF-DOUBT AND DISCOURAGEMENT (CRITICAL):
   - When the user expresses self-doubt, discouragement, or feeling behind (e.g., "I feel like I am not improving", "I have achieved nothing", "I am falling behind", "I feel stuck"):
     a) Recognize that they need encouragement and grounding, not another overwhelming task list.
     b) IMMEDIATELY call the `retrieve_relevant_achievements` tool to check their saved milestones and accomplishments.
     c) If achievements exist: Cite specific achievements, explain how they demonstrate real progress toward their goals, acknowledge the current setback without dismissing their feelings, and suggest ONE small, achievable next step.
     d) If NO achievements exist yet (count is 0): BE COMPLETELY HONEST. State gently: "I checked your saved records, and we haven't recorded any milestones yet. That does not mean you haven't grown—it just means your achievements aren't written down here yet. Let's write down one small win from this week together right now."
     e) NEVER invent achievements, fabricate progress statistics, or claim to remember things that are not stored in the database.

3. DAILY REFLECTION:
   - When the user shares a daily reflection:
     a) Extract completed tasks and achievements.
     b) Identify incomplete tasks and obstacles without judgment.
     c) If an accomplishment looks like a major milestone, suggest saving it as an achievement using `record_achievement`.
     d) Call `record_daily_reflection` with the summary, completed items, blockers, and one realistic priority for tomorrow.
     e) DO NOT mark a goal as completed unless the user explicitly confirms it was completed. Intention is not completion.

4. GENTLE MOMENTUM:
   - Never shame the user for missed goals or slow days.
   - When plans stall, recommend breaking tasks into smaller 10-15 minute increments.
   - Suggest only ONE priority for the next day to keep cognitive load low.

5. INTELLIGENT COMMAND GUIDANCE & MENTORSHIP:
   - When the user types natural language in the command line (e.g., "yearly goals are create an ai gent", "how am I doing", "what should I focus on"), do NOT reject it.
   - Provide contextual, helpful advice AND explicitly guide the user to the appropriate GoalFlow command:
     * When discussing creating or setting a goal -> Encourage them and point to `add-goal` (with suggested title/level/category).
     * When discussing checking or viewing goals -> Point to `list-goals`.
     * When discussing completing or changing a goal's status -> Point to `update-goal`.
     * When sharing their day's events, reflections, or obstacles -> Point to `reflect`.
     * When asking about past achievements or recording milestones -> Point to `achievements`.
     * When asking about statistics, completion rates, or stalled goals -> Point to `progress`.
     * When expressing self-doubt or needing motivation -> Retrieve achievements and suggest `encourage`.
     * When mentioning checking in for the day -> Point to `check-in`.
   - Format command guidance prominently, for example:
     💡 Recommended Command: `add-goal` (to configure title, level, and category step-by-step).

6. TOOL USAGE & CONVERSATIONAL COMPLETENESS:
   - Use `create_goal` to add new yearly, monthly, weekly, or daily goals when explicitly asked.
   - Use `list_goals` to review goals and their statuses.
   - Use `update_goal_status` to transition goals (pending -> in_progress -> completed -> abandoned).
   - Use `record_daily_reflection` to save reflections.
   - Use `record_achievement` to store milestones and wins.
   - Use `retrieve_relevant_achievements` to fetch stored wins.
   - Use `get_progress_summary` to get mathematical rollups and stalled goal alerts.
   - ALWAYS PROVIDE A NATURAL-LANGUAGE RESPONSE: After calling any tool, ALWAYS write a full, supportive conversational response to the user explaining what you did, summarizing what was saved/retrieved, and sharing your guidance. NEVER return only a tool call without a text message.
"""


def create_agent(model: Optional[str] = None) -> Agent:
    """Create a configured GoalFlow Agent using Google ADK."""
    selected_model = model or get_model_name()
    return Agent(
        name="goalflow_agent",
        model=selected_model,
        description="A grounded personal growth and reflection AI agent.",
        instruction=GOALFLOW_SYSTEM_INSTRUCTION,
        tools=GOALFLOW_TOOLS,
    )


class GoalFlowAgentService:
    """Manages the lifecycle, session, and runner for the GoalFlow ADK agent."""

    def __init__(self, model: Optional[str] = None, user_id: str = "default_user"):
        self.user_id = user_id
        self.model = model
        self._session_id: Optional[str] = None

        # Start a dedicated asyncio event loop in a background daemon thread.
        # This keeps the ADK Runner and GenAI HTTP connection pool alive and
        # prevents the event loop from being repeatedly destroyed and recreated.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # Initialize agent & runner inside the persistent event loop
        def _setup():
            self.agent = create_agent(model=self.model)
            self.session_service = InMemorySessionService()
            self.runner = Runner(
                app_name="goalflow",
                agent=self.agent,
                session_service=self.session_service,
            )

        future = asyncio.run_coroutine_threadsafe(self._async_wrapper(_setup), self._loop)
        future.result(timeout=10.0)

    @staticmethod
    async def _async_wrapper(fn):
        return fn()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def initialize_session(self) -> str:
        """Create a new conversational session if one does not already exist."""
        if not self._session_id:
            session = await self.session_service.create_session(
                app_name="goalflow",
                user_id=self.user_id,
            )
            self._session_id = session.id
        return self._session_id

    async def chat_async(self, message: str) -> AsyncGenerator[str, None]:
        """Send a natural-language message to the agent and stream the text response."""
        session_id = await self.initialize_session()
        content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )

        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=session_id,
            new_message=content,
        ):
            # Surface tool activity to user
            if hasattr(event, "get_function_calls") and event.get_function_calls():
                for fc in event.get_function_calls():
                    yield f"\n[Saving progress via {fc.name}...]\n"

            # Surface any model/runner errors
            if hasattr(event, "error_message") and event.error_message:
                yield f"\n[Error: {event.error_message}]\n"

            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        yield part.text

    def stream_chat(self, message: str, timeout: float = 40.0) -> str:
        """Stream chunks in real-time to stdout using the persistent loop."""
        import time
        q = queue.Queue()
        done_marker = object()

        async def _producer():
            try:
                session_id = await self.initialize_session()
                content = types.Content(
                    role="user",
                    parts=[types.Part(text=message)],
                )
                async for event in self.runner.run_async(
                    user_id=self.user_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    if hasattr(event, "get_function_calls") and event.get_function_calls():
                        for fc in event.get_function_calls():
                            q.put(f"\n[Saving progress via {fc.name}...]\n")
                    if hasattr(event, "error_message") and event.error_message:
                        q.put(f"\n[Error: {event.error_message}]\n")
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                q.put(part.text)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(done_marker)

        asyncio.run_coroutine_threadsafe(_producer(), self._loop)

        collected = []
        start_time = time.time()
        while True:
            remaining = max(0.1, timeout - (time.time() - start_time))
            try:
                item = q.get(timeout=remaining)
                if item is done_marker:
                    break
                if isinstance(item, Exception):
                    raise item
                sys.stdout.write(item)
                sys.stdout.flush()
                collected.append(item)
            except queue.Empty:
                print("\n[Request timed out. Continuing offline.]\n")
                break

        print()
        return "".join(collected)

    def chat(self, message: str) -> str:
        """Synchronous wrapper for chat_async to collect complete response."""
        async def _collect() -> str:
            collected = []
            async for chunk in self.chat_async(message):
                collected.append(chunk)
            return "".join(collected)

        future = asyncio.run_coroutine_threadsafe(_collect(), self._loop)
        return future.result(timeout=40.0)

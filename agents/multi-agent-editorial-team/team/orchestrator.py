"""Team Orchestrator: State machine coordinating Planner, Researcher, Writer, and Reviewer."""

import datetime
import logging
import os
import time
import uuid
from typing import Any, Callable, Dict, Optional

from .exceptions import InvalidTopicError
from .state import (
    AgentRole,
    EditorialMetrics,
    ReviewStatus,
    TeamState,
)
from .agents.planner import PlannerAgent
from .agents.researcher import ResearcherAgent
from .agents.writer import WriterAgent
from .agents.reviewer import ReviewerAgent

logger = logging.getLogger(__name__)


class EditorialOrchestrator:
    """Manages state transitions, communication protocols, and circuit breakers for the team."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        max_revisions: int = 2,
        pass_score: int = 85,
        mock_mode: bool = False,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.max_revisions = max(1, min(int(max_revisions or 2), 5))
        self.pass_score = max(50, min(int(pass_score or 85), 98))
        self.event_callback = event_callback

        # Determine if running in mock mode
        if mock_mode or not self.api_key or self.api_key == "your_gemini_api_key_here":
            self.mock_mode = True
            self.llm_caller = None
            logger.info("EditorialOrchestrator operating in OFFLINE MOCK MODE.")
        else:
            self.mock_mode = False
            self.llm_caller = self._init_gemini_caller()
            logger.info(f"EditorialOrchestrator connected to live Gemini: {self.model_name}")

        # Instantiate specialized agents
        self.planner = PlannerAgent(llm_caller=self.llm_caller)
        self.researcher = ResearcherAgent(llm_caller=self.llm_caller)
        self.writer = WriterAgent(llm_caller=self.llm_caller)
        self.reviewer = ReviewerAgent(pass_score=self.pass_score, llm_caller=self.llm_caller)

    def _init_gemini_caller(self) -> Optional[Callable[[str], str]]:
        """Initializes a unified Gemini text generator function."""
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            return lambda prompt: client.models.generate_content(
                model=self.model_name, contents=prompt
            ).text
        except ImportError:
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=self.api_key)
                model = legacy_genai.GenerativeModel(self.model_name)
                return lambda prompt: model.generate_content(prompt).text
            except ImportError:
                logger.warning("Google GenAI SDKs not found. Falling back to mock engine.")
                self.mock_mode = True
                return None

    def _dispatch_event(self, event_type: str, role: AgentRole, message: str, payload: Optional[Any] = None):
        """Notifies progress callback listener."""
        if self.event_callback:
            try:
                self.event_callback({
                    "event": event_type,
                    "role": role.value if isinstance(role, AgentRole) else str(role),
                    "message": message,
                    "payload": payload,
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
                })
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    def run(self, topic: str) -> TeamState:
        """Executes the collaborative editorial pipeline on a topic.

        Args:
            topic: The topic, question, or technology to research and draft.

        Returns:
            TeamState containing drafts, review verdicts, evidence, messages, and metrics.
        """
        if not topic or not str(topic).strip():
            raise InvalidTopicError("Editorial pipeline requires a non-empty topic string.")

        clean_topic = str(topic).strip()
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.datetime.now()
        start_perf = time.perf_counter()

        logger.info(f"[{run_id}] Launching Multi-Agent Pipeline for topic: '{clean_topic}'")

        state = TeamState(
            topic=clean_topic,
            max_revisions=self.max_revisions,
            pass_score=self.pass_score
        )

        # ======================================================================
        # Phase 1: Planner Agent
        # ======================================================================
        self._dispatch_event("agent_start", AgentRole.PLANNER, f"Decomposing topic '{clean_topic}' into structural plan.")
        plan = self.planner.plan(clean_topic)
        state.plan = plan
        state.record_message(
            sender=AgentRole.PLANNER,
            recipient=AgentRole.RESEARCHER,
            content=f"Plan generated: '{plan.title}' with {len(plan.key_sections)} sections and {len(plan.search_queries)} search queries.",
            turn=1
        )
        self._dispatch_event("agent_complete", AgentRole.PLANNER, f"Plan ready: '{plan.title}'", plan.model_dump())

        # ======================================================================
        # Phase 2: Researcher Agent
        # ======================================================================
        self._dispatch_event("agent_start", AgentRole.RESEARCHER, f"Executing web discovery for {len(plan.search_queries)} queries.")
        evidence = self.researcher.research(plan)
        state.evidence = evidence
        state.record_message(
            sender=AgentRole.RESEARCHER,
            recipient=AgentRole.WRITER,
            content=f"Evidence gathered: {len(evidence)} verified findings from online sources.",
            turn=1
        )
        self._dispatch_event("agent_complete", AgentRole.RESEARCHER, f"Gathered {len(evidence)} evidence items.", [e.model_dump() for e in evidence])

        # ======================================================================
        # Phase 3: Writer Agent (Initial Draft)
        # ======================================================================
        self._dispatch_event("agent_start", AgentRole.WRITER, "Drafting initial article (v1).")
        initial_draft = self.writer.write_initial_draft(plan, evidence)
        state.draft_history.append(initial_draft)
        state.current_draft = initial_draft
        state.record_message(
            sender=AgentRole.WRITER,
            recipient=AgentRole.REVIEWER,
            content=f"Draft v1 ready ({len(initial_draft)} characters) for editorial audit.",
            turn=1
        )
        self._dispatch_event("agent_complete", AgentRole.WRITER, f"Draft v1 completed ({len(initial_draft)} chars).")

        # ======================================================================
        # Phase 4: Reflection & Critique Loop (Circuit Breaker Managed)
        # ======================================================================
        iteration = 0
        while not state.is_approved and iteration <= self.max_revisions:
            iteration += 1
            turn_label = f"v{iteration}"

            self._dispatch_event("agent_start", AgentRole.REVIEWER, f"Auditing draft {turn_label} against quality rubric.")
            verdict = self.reviewer.review(state.current_draft, state.evidence, iteration)
            state.verdict_history.append(verdict)
            state.latest_verdict = verdict

            if verdict.status == ReviewStatus.APPROVED:
                state.is_approved = True
                state.record_message(
                    sender=AgentRole.REVIEWER,
                    recipient=AgentRole.ORCHESTRATOR,
                    content=f"Approved with Score {verdict.score}/100. Summary: {verdict.summary}",
                    turn=iteration
                )
                self._dispatch_event("agent_complete", AgentRole.REVIEWER, f"Draft {turn_label} APPROVED (Score: {verdict.score}/100)", verdict.model_dump())
                break

            # If not approved, check circuit breaker
            state.revision_turns += 1
            if state.revision_turns >= self.max_revisions:
                logger.warning(f"[{run_id}] Circuit breaker triggered: Max revisions reached ({self.max_revisions}). Halting revision loop.")
                state.record_message(
                    sender=AgentRole.ORCHESTRATOR,
                    recipient=AgentRole.WRITER,
                    content=f"Circuit breaker: Maximum revisions ({self.max_revisions}) reached. Finalizing best-effort publication.",
                    turn=iteration
                )
                self._dispatch_event("circuit_breaker", AgentRole.ORCHESTRATOR, f"Max revisions limit ({self.max_revisions}) reached. Finalizing publication.")
                break

            # Revise draft
            self._dispatch_event("agent_start", AgentRole.WRITER, f"Revising draft (v{iteration + 1}) to address Reviewer critiques.")
            revised = self.writer.revise_draft(state.current_draft, verdict)
            state.draft_history.append(revised)
            state.current_draft = revised
            state.record_message(
                sender=AgentRole.WRITER,
                recipient=AgentRole.REVIEWER,
                content=f"Revised draft v{iteration + 1} ready for re-review.",
                turn=iteration + 1
            )
            self._dispatch_event("agent_complete", AgentRole.WRITER, f"Draft v{iteration + 1} revised ({len(revised)} chars).")

        # ======================================================================
        # Finalization & Metrics
        # ======================================================================
        duration = round(time.perf_counter() - start_perf, 2)
        completed_at = datetime.datetime.now()
        final_score = state.latest_verdict.score if state.latest_verdict else 80

        state.metrics = EditorialMetrics(
            run_id=run_id,
            topic=clean_topic,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            revision_count=state.revision_turns,
            final_score=final_score,
            total_evidence_gathered=len(state.evidence),
            agent_messages_exchanged=len(state.messages),
            status="approved" if state.is_approved else "best_effort_published",
            mock_mode=self.mock_mode
        )

        logger.info(f"[{run_id}] Editorial pipeline completed in {duration}s. Final score: {final_score}/100. Status: {state.metrics.status}")
        return state

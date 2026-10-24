"""The handoff loop: three separate ADK agents, one shared memory.

The context-orchestration-engine owns the loop. For each plan step it compiles
a token-budgeted briefing from canonical state and hands it to ``ADKGateway``,
which runs that step's agent (``architect_agent``, ``jnr_agent`` or
``snr_agent``) in a brand-new ADK session with ``include_contents="none"``. An
agent sees its persona, the briefing and its own tool calls for this turn, and
nothing another agent said. Its JSON reply goes back to the engine as claims,
and the reconciler decides what becomes shared memory for the next agent.
"""

from __future__ import annotations

import asyncio

from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

import architect_agent.agent as architect
import jnr_agent.agent as junior
import snr_agent.agent as senior
from mock_llm import MockLlm
from shared_memory.engine import ContextCompiler, Orchestrator, SQLiteStore, WorkerConfig
from shared_memory.guardrails import GuardrailLog
from shared_memory.protocol import FIX_PIPELINE, PIPELINE, is_fix, live_model, model_for

APP_NAME = "engineering-team"
AGENTS = {m.NAME: m for m in (architect, junior, senior)}


class ADKGateway:
    """The engine's gateway interface, answered by ADK agents."""

    def __init__(self, agents: dict[str, LlmAgent]) -> None:
        self.agents = agents
        self.task_id = ""

    def complete(self, config: WorkerConfig, messages: list[dict]) -> str:
        briefing = messages[-1]["content"]
        try:
            return asyncio.run(self._run(self.agents[config.id], config.id, briefing))
        except Exception as exc:  # ADK/genai raise their own types (quota, auth, network)
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:300]
            raise RuntimeError(
                f"{config.id}: model call failed ({type(exc).__name__}): {first}. Finished "
                f"turns are saved; continue later with: python main.py --resume {self.task_id}"
            ) from exc

    async def _run(self, agent: LlmAgent, role: str, briefing: str) -> str:
        sessions = InMemorySessionService()
        session = await sessions.create_session(
            app_name=APP_NAME, user_id="team", state={"task_id": self.task_id, "role": role}
        )
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=sessions)
        reply = ""
        async for event in runner.run_async(
            user_id="team", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=briefing)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                reply = "".join(p.text or "" for p in event.content.parts)
        return reply


class TeamOrchestrator(Orchestrator):
    """The engine's loop with the step -> agent mapping of ``PIPELINE``."""

    def worker_for(self, step_index: int) -> WorkerConfig:
        role = PIPELINE[step_index % len(PIPELINE)].role
        return next(w for w in self.workers if w.id == role)

    def step(self, task_id: str):
        self.gateway.task_id = task_id
        return super().step(task_id)


def roster(mock: bool = False) -> list[WorkerConfig]:
    return [WorkerConfig(id=name, model="mock" if mock else model_for(name), api_key_env="GOOGLE_API_KEY")
            for name in AGENTS]


def build_team(
    store: SQLiteStore,
    mock: bool,
    log: GuardrailLog,
    budget: int = 1200,
    on_turn=None,
) -> TeamOrchestrator:
    agents = {name: module.build(MockLlm() if mock else live_model(model_for(name)), log)
              for name, module in AGENTS.items()}
    return TeamOrchestrator(
        roster(mock), ADKGateway(agents), store,
        compiler=ContextCompiler(budget=budget), on_turn=on_turn,
    )


def plan(objective: str = "") -> list[str]:
    """The five steps: build-from-scratch, or fix-a-bug for a cloned repository."""
    return [s.task for s in (FIX_PIPELINE if is_fix(objective) else PIPELINE)]

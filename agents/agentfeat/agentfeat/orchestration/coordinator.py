"""Central Hub: AgentCoordinator orchestrating tasks across specialized spoke agents."""

import logging
from pathlib import Path
from typing import Dict, Optional

from agentfeat.agents.analyzer_agent import AnalyzerAgent
from agentfeat.agents.base_agent import BaseAgent
from agentfeat.agents.developer_agent import DeveloperAgent
from agentfeat.agents.planner_agent import PlannerAgent
from agentfeat.agents.qa_agent import QAAgent
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan, FileChange
from agentfeat.orchestration.messages import AgentMessage, TaskStatus, TaskType
from agentfeat.orchestration.task_state import TaskState

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """The central Hub in the Hub-and-Spoke multi-agent architecture.

    Coordinates spoke agents, manages state, routes messages, enforces retry bounds,
    and aggregates execution outcomes.
    """

    def __init__(
        self,
        client: Optional[GeminiClient] = None,
        max_retries_per_agent: int = 2,
    ) -> None:
        self.client = client or GeminiClient()
        self.max_retries = max_retries_per_agent
        self.spokes: Dict[str, BaseAgent] = {}

        # Register default specialized spoke agents
        self.register_spoke(AnalyzerAgent())
        self.register_spoke(PlannerAgent(client=self.client))
        self.register_spoke(DeveloperAgent(client=self.client))
        self.register_spoke(QAAgent())

    def register_spoke(self, agent: BaseAgent) -> None:
        """Register or replace a spoke agent connected to the Hub."""
        self.spokes[agent.name] = agent

    def dispatch(self, message: AgentMessage, state: TaskState) -> AgentMessage:
        """Route a message to the target spoke agent, handling retries and errors."""
        recipient = message.recipient
        agent = self.spokes.get(recipient)

        if not agent:
            error_response = AgentMessage.create_error(
                message,
                sender="hub",
                error_msg=f"No spoke agent registered with name '{recipient}'",
            )
            state.log(state.current_stage, "hub", "agent_not_found", {"recipient": recipient})
            return error_response

        # Log dispatch
        state.log(
            stage=state.current_stage,
            agent=recipient,
            event="task_dispatched",
            details={"task_type": message.task_type.value},
        )

        # Execute with bounded retries (initial attempt + up to max_retries)
        response: Optional[AgentMessage] = None
        for attempt in range(self.max_retries + 1):
            response = agent.execute(message)
            if response.status == TaskStatus.SUCCESS:
                state.log(
                    stage=state.current_stage,
                    agent=recipient,
                    event="task_succeeded",
                    details={"task_type": message.task_type.value},
                )
                return response

            # If not yet at max retries, record retry event
            if attempt < self.max_retries:
                retry_num = state.increment_retry(recipient)
                state.log(
                    stage=state.current_stage,
                    agent=recipient,
                    event="task_failed_retrying",
                    details={"error": response.error, "retry_attempt": retry_num},
                )
            else:
                state.log(
                    stage=state.current_stage,
                    agent=recipient,
                    event="task_failed_exhausted",
                    details={"error": response.error, "total_attempts": attempt + 1},
                )

        return response or AgentMessage.create_error(
            message,
            sender="hub",
            error_msg=f"Spoke agent '{recipient}' failed after {self.max_retries} retries",
        )

    def run_workflow(self, feature_request: str, target_dir: Path) -> TaskState:
        """Execute the linear Hub-and-Spoke feature engineering workflow."""
        resolved_dir = target_dir.resolve()
        state = TaskState(feature_request=feature_request, target_dir=str(resolved_dir))
        state.log("init", "hub", "workflow_started", {"request": feature_request})

        # --- Stage 1: Codebase Analysis (Analyzer Spoke) ---
        state.current_stage = "analyzing"
        analyze_req = AgentMessage.create_request(
            task_id=state.task_id,
            sender="hub",
            recipient="analyzer",
            task_type=TaskType.ANALYZE,
            payload={"target_dir": str(resolved_dir), "query": feature_request},
        )
        analyze_resp = self.dispatch(analyze_req, state)

        if analyze_resp.status != TaskStatus.SUCCESS:
            state.current_stage = "failed"
            state.log("analyzing", "hub", "workflow_aborted", {"reason": analyze_resp.error})
            return state

        state.codebase_summary = CodebaseSummary.model_validate(
            analyze_resp.payload["codebase_summary"]
        )

        # --- Stage 2: Feature Planning (Planner Spoke) ---
        state.current_stage = "planning"
        plan_req = AgentMessage.create_request(
            task_id=state.task_id,
            sender="hub",
            recipient="planner",
            task_type=TaskType.PLAN,
            payload={
                "feature_request": feature_request,
                "codebase_summary": state.codebase_summary.model_dump(),
            },
        )
        plan_resp = self.dispatch(plan_req, state)

        if plan_resp.status != TaskStatus.SUCCESS:
            state.current_stage = "failed"
            state.log("planning", "hub", "workflow_aborted", {"reason": plan_resp.error})
            return state

        state.plan = FeaturePlan.model_validate(plan_resp.payload["plan"])

        # --- Stage 3: Code Generation (Developer Spoke) ---
        state.current_stage = "developing"
        dev_req = AgentMessage.create_request(
            task_id=state.task_id,
            sender="hub",
            recipient="developer",
            task_type=TaskType.DEVELOP,
            payload={
                "feature_request": feature_request,
                "plan": state.plan.model_dump(),
                "codebase_summary": state.codebase_summary.model_dump(),
                "target_dir": str(resolved_dir),
            },
        )
        dev_resp = self.dispatch(dev_req, state)

        if dev_resp.status != TaskStatus.SUCCESS:
            state.current_stage = "failed"
            state.log("developing", "hub", "workflow_aborted", {"reason": dev_resp.error})
            return state

        state.changes = [FileChange.model_validate(c) for c in dev_resp.payload.get("changes", [])]

        # --- Stage 4: Testing & QA Review (QA Spoke) ---
        state.current_stage = "qa"
        qa_req = AgentMessage.create_request(
            task_id=state.task_id,
            sender="hub",
            recipient="qa",
            task_type=TaskType.QA,
            payload={
                "changes": [c.model_dump() for c in state.changes],
                "target_dir": str(resolved_dir),
            },
        )
        qa_resp = self.dispatch(qa_req, state)

        if qa_resp.status == TaskStatus.SUCCESS:
            state.qa_passed = qa_resp.payload.get("passed", False)
            state.qa_findings = qa_resp.payload.get("findings", [])
            # Update changes with QA validation metadata
            if "validated_changes" in qa_resp.payload:
                state.changes = [
                    FileChange.model_validate(c) for c in qa_resp.payload["validated_changes"]
                ]

        state.current_stage = "review"
        state.log("review", "hub", "workflow_completed_ready_for_review")
        return state

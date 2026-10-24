"""Planner Spoke Agent: Architecture blueprinting and feature breakdown."""

from typing import Optional

from agentfeat.agents.base_agent import BaseAgent
from agentfeat.core.planner import FeaturePlanner
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan
from agentfeat.orchestration.messages import AgentMessage


class PlannerAgent(BaseAgent):
    """Spoke agent responsible for generating the structured feature plan."""

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        super().__init__(name="planner", role="Architectural Feature Planning")
        self.client = client or GeminiClient()

    def process(self, message: AgentMessage) -> AgentMessage:
        feature_request = message.payload.get("feature_request", "")
        summary_data = message.payload.get("codebase_summary")

        if not feature_request:
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg="Missing required 'feature_request' in payload",
            )

        if not summary_data:
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg="Missing required 'codebase_summary' in payload",
            )

        codebase_summary = CodebaseSummary.model_validate(summary_data)
        planner = FeaturePlanner(client=self.client)
        plan = planner.create_plan(feature_request, codebase_summary)

        return AgentMessage.create_response(
            message,
            sender=self.name,
            payload={"plan": plan.model_dump()},
        )

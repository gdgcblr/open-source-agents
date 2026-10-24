"""Developer Spoke Agent: Synthesizes production code, test files, and unified diffs."""

from pathlib import Path
from typing import Optional

from agentfeat.agents.base_agent import BaseAgent
from agentfeat.core.generator import CodeGenerator
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan
from agentfeat.orchestration.messages import AgentMessage


class DeveloperAgent(BaseAgent):
    """Spoke agent responsible for generating proposed code modifications and diffs."""

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        super().__init__(name="developer", role="Code Implementation & Diff Generation")
        self.client = client or GeminiClient()

    def process(self, message: AgentMessage) -> AgentMessage:
        feature_request = message.payload.get("feature_request", "")
        plan_data = message.payload.get("plan")
        summary_data = message.payload.get("codebase_summary")
        target_dir_str = message.payload.get("target_dir", ".")

        if not plan_data:
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg="Missing required 'plan' in payload",
            )

        target_dir = Path(target_dir_str).resolve()
        plan = FeaturePlan.model_validate(plan_data)
        summary = CodebaseSummary.model_validate(summary_data) if summary_data else CodebaseSummary(root_path=str(target_dir))

        generator = CodeGenerator(target_dir=target_dir, client=self.client)
        changes = generator.generate_changes(feature_request, plan, summary)

        # DeveloperAgent returns proposed changes; it NEVER writes to disk!
        return AgentMessage.create_response(
            message,
            sender=self.name,
            payload={"changes": [c.model_dump() for c in changes]},
        )

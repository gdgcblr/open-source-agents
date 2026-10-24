"""Analyzer Spoke Agent: Codebase discovery, manifest parsing, and context extraction."""

from pathlib import Path
from typing import Optional

from agentfeat.agents.base_agent import BaseAgent
from agentfeat.core.analyzer import CodebaseAnalyzer
from agentfeat.models.schemas import CodebaseSummary
from agentfeat.orchestration.messages import AgentMessage


class AnalyzerAgent(BaseAgent):
    """Spoke agent responsible for analyzing the repository structure."""

    def __init__(self) -> None:
        super().__init__(name="analyzer", role="Codebase Discovery & Context Extraction")

    def process(self, message: AgentMessage) -> AgentMessage:
        target_dir_str = message.payload.get("target_dir", ".")
        query = message.payload.get("query", "")

        target_path = Path(target_dir_str).resolve()
        if not target_path.is_dir():
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg=f"Target directory does not exist: {target_dir_str}",
            )

        analyzer = CodebaseAnalyzer(target_path)
        summary = analyzer.analyze(query)

        return AgentMessage.create_response(
            message,
            sender=self.name,
            payload={"codebase_summary": summary.model_dump()},
        )

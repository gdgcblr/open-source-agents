"""Feature planner: generates structured implementation plans using Gemini."""

from typing import Optional

from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan


PLANNER_SYSTEM_PROMPT = """You are AgentFeat's Principal Software Architect.
Your task is to analyze a developer's feature request alongside their existing codebase context, and produce a rigorous, realistic, and production-ready implementation plan.

Follow these strict principles:
1. Modularity & Isolation: Prefer adding new dedicated modules or clean extensions over monolithic modifications.
2. Grounded in Codebase: Respect existing project structure, language idioms, style conventions, and dependency managers.
3. Test-First Rigor: Every feature MUST include a dedicated test plan and automated test file step (e.g. pytest, jest, etc.).
4. Safe Ordering: Sequence the steps logically (e.g. dependencies -> interfaces/models -> core logic -> integration -> tests).
5. Concrete Paths: Always specify real, sensible relative file paths for each step.
"""


class FeaturePlanner:
    """Orchestrates feature planning with Google Gemini."""

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        self.client = client or GeminiClient()

    def create_plan(self, feature_request: str, codebase: CodebaseSummary) -> FeaturePlan:
        """Generate a structured FeaturePlan based on user request and scanned codebase."""
        # Assemble context string
        context_parts = [
            f"=== TARGET CODEBASE CONTEXT ===",
            f"Repository Root: {codebase.root_path}",
            f"Detected Languages: {', '.join(codebase.languages) if codebase.languages else 'None detected'}",
            f"Detected Frameworks: {', '.join(codebase.frameworks) if codebase.frameworks else 'None detected'}",
            f"Manifests: {', '.join(codebase.manifest_files) if codebase.manifest_files else 'None'}",
            "",
            "--- FILE TREE ---",
            codebase.file_tree,
            "",
            "--- KEY FILE SNIPPETS ---",
        ]

        for fc in codebase.relevant_files[:5]:
            context_parts.append(f"File: {fc.path} ({fc.language})")
            context_parts.append("```")
            context_parts.append(fc.content[:2000] if fc.content else "(empty)")
            context_parts.append("```\n")

        context_parts.extend([
            "=== USER FEATURE REQUEST ===",
            feature_request,
            "",
            "Produce the complete structured implementation plan for this feature.",
        ])

        full_prompt = "\n".join(context_parts)

        plan = self.client.generate_structured(
            prompt=full_prompt,
            response_schema=FeaturePlan,
            system_instruction=PLANNER_SYSTEM_PROMPT,
        )

        return plan

"""Code generator: writes production-grade code, tests, and diffs using Gemini."""

from pathlib import Path
from typing import List, Optional

from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan, FileChange, PlanStep
from agentfeat.utils.file_ops import generate_diff, read_file_safe


GENERATOR_SYSTEM_PROMPT = """You are AgentFeat's Senior Staff Engineer.
Your job is to generate production-ready, clean, well-tested code for a specified file step in a feature implementation plan.

Rules:
1. Complete Code: Return the ENTIRE file content. Do not use placeholders like '// ... existing code ...' or 'pass # TODO'.
2. Idiomatic & Clean: Include proper type annotations, clear docstrings, and robust error handling.
3. Tests Included: If generating a test file, write real, executable tests covering standard, edge, and failure scenarios.
4. Output format: Output ONLY the raw code for the file without markdown code fences (no ```python or ``` at the beginning/end).
"""


class CodeGenerator:
    """Generates file modifications, additions, and diffs."""

    def __init__(self, target_dir: Path, client: Optional[GeminiClient] = None) -> None:
        self.target_dir = target_dir.resolve()
        self.client = client or GeminiClient()

    def generate_changes(
        self,
        feature_request: str,
        plan: FeaturePlan,
        codebase: CodebaseSummary,
    ) -> List[FileChange]:
        """Generate code changes for all steps in the plan."""
        changes: List[FileChange] = []

        # Deduplicate steps targeting the same file
        processed_files = set()

        for step in plan.steps:
            if step.target_file in processed_files:
                continue
            processed_files.add(step.target_file)

            change = self._generate_file_change(step, feature_request, plan, codebase)
            changes.append(change)

        return changes

    def _generate_file_change(
        self,
        step: PlanStep,
        feature_request: str,
        plan: FeaturePlan,
        codebase: CodebaseSummary,
    ) -> FileChange:
        """Generate a single file change based on a plan step."""
        target_path = self.target_dir / step.target_file
        original_content: Optional[str] = None
        action = step.action if step.action in ("create", "modify", "delete") else "create"

        if target_path.is_file():
            orig_text, _ = read_file_safe(target_path)
            original_content = orig_text
            if action != "delete":
                action = "modify"
        else:
            if action != "delete":
                action = "create"

        if action == "delete":
            diff = generate_diff(original_content, "", step.target_file)
            return FileChange(
                file_path=step.target_file,
                action="delete",
                description=step.description,
                original_content=original_content,
                new_content="",
                diff=diff,
            )

        # Build prompt for LLM
        prompt_parts = [
            f"=== TARGET FILE: {step.target_file} ===",
            f"Action: {action.upper()}",
            f"Step Title: {step.title}",
            f"Step Requirements: {step.description}",
            f"Feature Request: {feature_request}",
            f"Architecture Notes: {plan.architecture_notes}",
            "",
        ]

        if original_content:
            prompt_parts.extend([
                "--- EXISTING FILE CONTENT ---",
                original_content,
                "--- END EXISTING FILE CONTENT ---",
                "",
                "Generate the full updated file content incorporating the new feature while preserving existing valid functionality.",
            ])
        else:
            prompt_parts.extend([
                "This is a new file. Generate the complete, production-ready implementation from scratch.",
            ])

        prompt = "\n".join(prompt_parts)

        # Generate new content
        raw_code = self.client.generate_text(
            prompt=prompt,
            system_instruction=GENERATOR_SYSTEM_PROMPT,
        )

        # Strip markdown fences if the model wrapped them
        cleaned_code = self._strip_markdown_fences(raw_code)

        # Generate diff
        diff = generate_diff(original_content, cleaned_code, step.target_file)

        return FileChange(
            file_path=step.target_file,
            action=action,
            description=step.description,
            original_content=original_content,
            new_content=cleaned_code,
            diff=diff,
        )

    def _strip_markdown_fences(self, text: str) -> str:
        """Strip starting and ending markdown code block fences if present."""
        lines = text.strip().splitlines()
        if not lines:
            return ""

        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]

        return "\n".join(lines).strip() + "\n"

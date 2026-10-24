"""PR reporter: generates standardized GitHub Pull Request descriptions and changelogs."""

from typing import List
from agentfeat.models.schemas import FeaturePlan, FileChange


class PRReporter:
    """Builds comprehensive markdown PR descriptions and commit messages."""

    @staticmethod
    def generate_pr_markdown(
        feature_request: str,
        plan: FeaturePlan,
        changes: List[FileChange],
        applied: bool,
    ) -> str:
        """Create a GitHub pull request description following best practices."""
        status_tag = "Applied to workspace" if applied else "Proposed / Dry-run"

        lines = [
            f"# Feature: {plan.feature_title}",
            "",
            f"> **Prompt**: {feature_request}",
            f"> **Status**: {status_tag}",
            "",
            "## 📖 Summary",
            plan.summary,
            "",
            "## 🏗️ Architecture & Design Notes",
            plan.architecture_notes,
            "",
            "## 📦 Changed & Created Files",
            "| File | Action | Description |",
            "| --- | --- | --- |",
        ]

        for c in changes:
            lines.append(f"| `{c.file_path}` | `{c.action.upper()}` | {c.description} |")

        if plan.new_dependencies:
            lines.extend([
                "",
                "## ⚙️ Dependencies",
                "The following packages were identified or added:",
            ])
            for dep in plan.new_dependencies:
                lines.append(f"- `{dep}`")

        lines.extend([
            "",
            "## 🧪 Verification & Test Strategy",
            plan.test_strategy,
            "",
            "## ⚠️ Risks & Considerations",
            plan.risk_assessment,
            "",
            "---",
            "*Generated automatically by [AgentFeat](https://github.com/gdgcblr/open-source-agents) — AI-powered feature development agent.*",
        ])

        return "\n".join(lines)

    @staticmethod
    def generate_commit_message(plan: FeaturePlan) -> str:
        """Generate a conventional commit message."""
        title_slug = plan.feature_title.lower().replace(" ", "-")
        return f"feat: implement {title_slug}\n\n{plan.summary}"

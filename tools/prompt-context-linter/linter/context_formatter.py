"""Dynamic structured context builder and prompt formatter."""

from typing import Any, Dict, List, Optional


class ContextFormatter:
    """Formats modular prompt components into structured, token-efficient LLM contexts."""

    def __init__(self, delimiter_style: str = "markdown"):
        """Args:
            delimiter_style: 'markdown' (uses headings) or 'xml' (uses <tags>).
        """
        self.delimiter_style = delimiter_style.lower()

    def build_context(
        self,
        system_role: str,
        instructions: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, str]]] = None,
        examples: Optional[List[Dict[str, str]]] = None,
        context_documents: Optional[Dict[str, str]] = None,
        user_query: Optional[str] = None,
    ) -> str:
        """Assembles a modular prompt context.

        Args:
            system_role: Primary role and persona.
            instructions: Key behavioral rules or constraints.
            tools: Registered tool names and usage descriptions.
            examples: Few-shot exemplars with 'input' and 'output'.
            context_documents: Mapping of document title/filename to content.
            user_query: End-user instruction or query.

        Returns:
            Clean, formatted multi-section prompt string.
        """
        sections: List[str] = []

        if self.delimiter_style == "xml":
            # XML Tag Style
            sections.append(f"<system>\n{system_role.strip()}\n</system>")

            if instructions:
                rule_lines = "\n".join(f"- {r.strip()}" for r in instructions if r.strip())
                sections.append(f"<instructions>\n{rule_lines}\n</instructions>")

            if tools:
                tool_lines = []
                for t in tools:
                    name = t.get("name", "tool")
                    desc = t.get("description", "")
                    tool_lines.append(f"Tool: {name}\nDescription: {desc}")
                sections.append(f"<tools>\n" + "\n\n".join(tool_lines) + "\n</tools>")

            if examples:
                ex_lines = []
                for idx, ex in enumerate(examples, 1):
                    inp = ex.get("input", "")
                    out = ex.get("output", "")
                    ex_lines.append(f"Example {idx}:\nUser: {inp}\nAssistant: {out}")
                sections.append(f"<examples>\n" + "\n\n".join(ex_lines) + "\n</examples>")

            if context_documents:
                doc_lines = []
                for title, content in context_documents.items():
                    doc_lines.append(f'<document title="{title}">\n{content.strip()}\n</document>')
                sections.append(f"<context>\n" + "\n\n".join(doc_lines) + "\n</context>")

            if user_query:
                sections.append(f"<user_query>\n{user_query.strip()}\n</user_query>")

        else:
            # Markdown Header Style
            sections.append(f"# System Role\n{system_role.strip()}")

            if instructions:
                rule_lines = "\n".join(f"- {r.strip()}" for r in instructions if r.strip())
                sections.append(f"## Instructions & Constraints\n{rule_lines}")

            if tools:
                tool_lines = []
                for t in tools:
                    name = t.get("name", "tool")
                    desc = t.get("description", "")
                    tool_lines.append(f"### Tool: `{name}`\n{desc}")
                sections.append("## Available Tools\n" + "\n\n".join(tool_lines))

            if examples:
                ex_lines = []
                for idx, ex in enumerate(examples, 1):
                    inp = ex.get("input", "")
                    out = ex.get("output", "")
                    ex_lines.append(f"#### Example {idx}\n**Input:**\n{inp}\n\n**Expected Output:**\n{out}")
                sections.append("## Few-Shot Exemplars\n" + "\n\n".join(ex_lines))

            if context_documents:
                doc_lines = []
                for title, content in context_documents.items():
                    doc_lines.append(f"### Document: {title}\n```\n{content.strip()}\n```")
                sections.append("## Reference Context\n" + "\n\n".join(doc_lines))

            if user_query:
                sections.append(f"## User Request\n{user_query.strip()}")

        return "\n\n".join(sections).strip() + "\n"

"""
Documentation Generator — Uses Google Gemini to produce structured
markdown documentation from analyzed and categorized code.

Generates two categories of documentation:
1. User Docs  (docs_output/user-docs/)  — Installation, usage, API reference, config
2. Dev Docs   (docs_output/dev-docs/)   — Architecture, modules, internals, contributing

Each category gets an index.md and topic-specific pages.
"""

import json
import os
import warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=FutureWarning)
    import google.generativeai as genai

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config

console = Console()


# =============================================================================
# Prompt Templates
# =============================================================================

USER_DOCS_PROMPT = """\
You are a technical documentation writer. Generate comprehensive USER-FACING
documentation for a software project.

User documentation is for people who USE the software — they need to know:
- What the project does (overview)
- How to install it (prerequisites + step-by-step)
- How to configure it (environment variables, config files)
- How to use it (commands, API calls, examples)
- API reference for public functions/classes
- Troubleshooting / FAQ

Use clear, professional Markdown formatting with proper headings, code blocks,
and tables where appropriate.

Here is the codebase analysis with files categorized as user-facing:

{codebase_content}

Generate the documentation as a single Markdown document. Include:
1. A project overview section
2. Installation & setup
3. Configuration reference (if config files exist)
4. Usage guide with real examples based on the actual code
5. API Reference (public classes and functions only)
6. Known limitations (based on what you can infer from the code)

Do NOT make up features that don't exist in the code. Only document what you
can actually see in the codebase analysis above.
"""

DEV_DOCS_PROMPT = """\
You are a technical documentation writer. Generate comprehensive DEVELOPER
documentation for a software project.

Developer documentation is for people who CONTRIBUTE to or MAINTAIN the
software — they need to know:
- Architecture overview and design decisions
- Module-by-module breakdown (what each file/module does)
- Key classes, their responsibilities, and relationships
- Internal data flow and processing pipeline
- How to extend the codebase (adding new features/modules)
- Testing strategy and how to run tests
- Code style and conventions used

Use clear, professional Markdown formatting with proper headings, code blocks,
and tables where appropriate.

Here is the codebase analysis with files categorized as developer-facing:

{codebase_content}

Generate the documentation as a single Markdown document. Include:
1. Architecture overview with a high-level description of how components connect
2. Module reference (every source file, its purpose, key classes/functions)
3. Internal API documentation (private functions, helper utilities)
4. Data flow description
5. Extension guide (how to add new analyzers, features, etc.)
6. Testing guide

Do NOT make up features that don't exist in the code. Only document what you
can actually see in the codebase analysis above.
"""

INDEX_PROMPT = """\
You are a documentation writer. Given the following list of documentation pages,
generate a clean index/table-of-contents page in Markdown.

Category: {category}
Pages:
{pages_list}

Generate a Markdown page with:
1. A title (e.g., "User Documentation" or "Developer Documentation")
2. A brief description of what this documentation covers
3. A table of contents with links to each page
4. Use relative markdown links (e.g., [Page Title](./page-name.md))
"""


def generate_documentation(
    analyses: list[dict],
    categorization: dict,
    codebase_map: dict,
    config: Config,
) -> dict:
    """
    Generate full documentation using Gemini.

    Args:
        analyses: List of file analysis dicts from analyzer.analyze_codebase().
        categorization: Dict mapping file paths to categories from categorizer.
        codebase_map: The raw codebase map from scanner.scan_codebase().
        config: Configuration object.

    Returns:
        A dict with the generated documentation:
        {
            "user_docs": {"filename.md": "content", ...},
            "dev_docs": {"filename.md": "content", ...},
            "metadata": {...},
        }
    """
    genai.configure(api_key=config.gemini_api_key)
    model = genai.GenerativeModel(config.gemini_model)

    # Separate analyses into user-facing and dev-facing
    user_analyses = []
    dev_analyses = []

    for analysis in analyses:
        path = analysis["path"]
        cat_info = categorization.get(path, {"category": "both"})
        category = cat_info.get("category", "both")

        if category == "user":
            user_analyses.append(analysis)
        elif category == "dev":
            dev_analyses.append(analysis)
        elif category == "both":
            user_analyses.append(analysis)
            dev_analyses.append(analysis)

    result = {
        "user_docs": {},
        "dev_docs": {},
        "metadata": {
            "total_files_analyzed": len(analyses),
            "user_files": len(user_analyses),
            "dev_files": len(dev_analyses),
            "root_path": codebase_map.get("root_path", ""),
        },
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # Generate User Documentation
        if user_analyses:
            task = progress.add_task("Generating user documentation...", total=None)
            user_content = _build_content_for_prompt(user_analyses)
            user_doc = _call_gemini(model, USER_DOCS_PROMPT.format(codebase_content=user_content))

            if user_doc:
                result["user_docs"]["user-guide.md"] = user_doc
            progress.update(task, description="User documentation generated ✓")

        # Generate Dev Documentation
        if dev_analyses:
            task = progress.add_task("Generating developer documentation...", total=None)
            dev_content = _build_content_for_prompt(dev_analyses)
            dev_doc = _call_gemini(model, DEV_DOCS_PROMPT.format(codebase_content=dev_content))

            if dev_doc:
                result["dev_docs"]["developer-guide.md"] = dev_doc
            progress.update(task, description="Developer documentation generated ✓")

        # Generate index pages
        task = progress.add_task("Generating index pages...", total=None)

        if result["user_docs"]:
            pages_list = "\n".join(f"- {name}" for name in result["user_docs"].keys())
            index_content = _call_gemini(
                model,
                INDEX_PROMPT.format(category="User Documentation", pages_list=pages_list),
            )
            if index_content:
                result["user_docs"]["index.md"] = index_content

        if result["dev_docs"]:
            pages_list = "\n".join(f"- {name}" for name in result["dev_docs"].keys())
            index_content = _call_gemini(
                model,
                INDEX_PROMPT.format(category="Developer Documentation", pages_list=pages_list),
            )
            if index_content:
                result["dev_docs"]["index.md"] = index_content

        progress.update(task, description="Index pages generated ✓")

    return result


def write_documentation(docs: dict, output_dir: str) -> list[str]:
    """
    Write generated documentation to disk.

    Args:
        docs: The output dict from generate_documentation().
        output_dir: Path to the output directory.

    Returns:
        List of file paths that were written.
    """
    output = Path(output_dir)
    written_files = []

    # Write user docs
    user_dir = output / "user-docs"
    user_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in docs.get("user_docs", {}).items():
        filepath = user_dir / filename
        filepath.write_text(content, encoding="utf-8")
        written_files.append(str(filepath))

    # Write dev docs
    dev_dir = output / "dev-docs"
    dev_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in docs.get("dev_docs", {}).items():
        filepath = dev_dir / filename
        filepath.write_text(content, encoding="utf-8")
        written_files.append(str(filepath))

    # Write metadata
    metadata_path = output / ".codelens-state.json"
    metadata_path.write_text(
        json.dumps(docs.get("metadata", {}), indent=2),
        encoding="utf-8",
    )
    written_files.append(str(metadata_path))

    return written_files


def _build_content_for_prompt(analyses: list[dict], max_chars: int = 60000) -> str:
    """
    Build a text representation of file analyses suitable for the LLM prompt.
    Similar to condense_for_llm but with more detail for doc generation.
    """
    sections = []
    total_chars = 0

    for analysis in analyses:
        section_lines = []
        section_lines.append(f"### File: `{analysis['path']}` (Language: {analysis['language']})")

        if analysis.get("module_docstring"):
            section_lines.append(f"**Module docstring:** {analysis['module_docstring']}")

        # Classes
        for cls in analysis.get("classes", []):
            vis = "🔒 private" if cls.get("is_private") else "🌐 public"
            bases = f" (extends: {', '.join(cls['bases'])})" if cls.get("bases") else ""
            section_lines.append(f"- **Class `{cls['name']}`** [{vis}]{bases}")
            if cls.get("docstring"):
                section_lines.append(f"  - Docstring: {cls['docstring']}")
            for method in cls.get("methods", []):
                m_vis = "private" if method.get("is_private") else "public"
                async_tag = "async " if method.get("is_async") else ""
                args_str = ", ".join(
                    a["name"] + (f": {a['type']}" if a.get("type") else "")
                    for a in method.get("args", [])
                )
                ret = f" → {method['return_type']}" if method.get("return_type") else ""
                section_lines.append(f"  - Method: `{async_tag}{method['name']}({args_str}){ret}` [{m_vis}]")
                if method.get("docstring"):
                    section_lines.append(f"    - {method['docstring'][:200]}")

        # Functions
        for func in analysis.get("functions", []):
            vis = "🔒 private" if func.get("is_private") else "🌐 public"
            async_tag = "async " if func.get("is_async") else ""
            args_str = ", ".join(
                a["name"] + (f": {a['type']}" if a.get("type") else "")
                for a in func.get("args", [])
            )
            ret = f" → {func['return_type']}" if func.get("return_type") else ""
            section_lines.append(f"- **Function `{async_tag}{func['name']}({args_str}){ret}`** [{vis}]")
            if func.get("docstring"):
                section_lines.append(f"  - {func['docstring'][:200]}")

        # Imports
        if analysis.get("imports"):
            section_lines.append(f"- **Imports:** {', '.join(analysis['imports'][:20])}")

        # Config keys
        if analysis.get("config_keys"):
            section_lines.append(f"- **Config keys:** {', '.join(analysis['config_keys'][:20])}")

        section_text = "\n".join(section_lines)

        if total_chars + len(section_text) > max_chars:
            sections.append(f"\n*(... {len(analyses) - len(sections)} more files truncated for brevity)*")
            break

        sections.append(section_text)
        total_chars += len(section_text)

    return "\n\n".join(sections)


def _call_gemini(model, prompt: str) -> str | None:
    """
    Call Gemini with error handling and retry logic.
    Returns the text response or None on failure.
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )
            return response.text
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                console.print(f"[yellow]Gemini API error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...[/yellow]")
                import time
                time.sleep(wait_time)
            else:
                console.print(f"[red]Gemini API failed after {max_retries} attempts:[/red] {e}")
                return None

"""Project context and repository discovery for MergeReady."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib
from typing import Any, Optional


MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_FILE_COUNT = 500

FALLBACK_TEMPLATE_README = """# [Project Name]

> [One-sentence summary of what this project does and the value it provides.]

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Explain what specific problem or challenge this project addresses.
- **Intended Users**: Who is this tool or agent built for? (e.g., developers, researchers, operations engineers).

### Key Features
- Feature 1: Brief description of the capability.
- Feature 2: Brief description of the capability.
- Feature 3: Brief description of the capability.

---

## Technical Stack

List the primary frameworks, languages, models, and external services used:
- **Language & Runtime**: e.g., Python 3.11+ / Node.js 20+ / TypeScript
- **Agent Framework / Core Library**: e.g., Google ADK / LangGraph / CrewAI / OpenAI Agents SDK / Model Context Protocol (MCP) / Vanilla script
- **Models**: e.g., Gemini 2.5 Flash / GPT-4o / Claude 3.5 Sonnet / Local model (e.g., Ollama)
- **External APIs / Tools**: e.g., Tavily Search / GitHub API / SQLite

---

## Architecture & Data Flow

```
[User Input] --> [Agent / Runner] --> [LLM / Reasoning Loop]
                         |
                         +--> [Tool / External API / MCP Server]
                         |
[Structured Output] <-- [Agent Response]
```

---

## Prerequisites

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/<project-slug>   # or tools/<project-slug>
   ```

2. **Set up the virtual environment / install dependencies:**
   - For Python:
     ```bash
     python -m venv .venv
     .venv\\Scripts\\activate
     pip install -r requirements.txt
     ```
   - For Node.js / TypeScript:
     ```bash
     npm install
     ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `API_KEY` | Yes | *None* | API key for the primary LLM provider |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Identifier for the LLM model to use |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run

---

## Example Input & Output

### Example Input
```
"Analyze the repository structure of gdgcblr/open-source-agents and list the core directories."
```

### Example Output
```
Analysis completed:
- agents/: Contains community AI agents.
- tools/: Contains shared developer utilities and MCP servers.
- template/: Standardized documentation and environment templates.
```

---

## How to Test

---

## Known Limitations

---

## Security & Privacy Considerations

---

## Future Improvements

---

## License
"""

FALLBACK_TEMPLATE_ENV = """# Example Environment Configuration
# Copy this file to .env and substitute your own configuration values.
# NEVER commit real API keys, secrets, or .env files to Git.

# --- LLM Providers ---
# GEMINI_API_KEY=your_gemini_api_key_here
# OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=your_anthropic_api_key_here

# --- Optional Project Settings ---
# LOG_LEVEL=info
# PORT=8000
"""


class ProjectContext:
    """Encapsulates the state and files of the target contribution under validation."""

    def __init__(self, project_path: Path, base_ref: Optional[str] = None) -> None:
        self.project_path = project_path.resolve()
        if not self.project_path.exists() or not self.project_path.is_dir():
            raise ValueError(f"Project directory does not exist: {project_path}")

        self.base_ref = base_ref
        self.repo_root = self._find_repo_root()
        self.category, self.slug = self._determine_category_and_slug()
        self.config_errors: list[str] = []
        self.rules_config = self._load_rules_config()
        self.template_readme = self._load_template_readme()
        self.template_env = self._load_template_env()
        self.limit_exceeded_file_count: bool = False
        self.oversized_files: list[tuple[str, int]] = []
        self.rejected_symlinks: list[tuple[str, str]] = []
        self.unreadable_files: list[tuple[str, str]] = []
        self.files = self._collect_files()
        self.tracked_files = self._collect_tracked_files()

    def _find_repo_root(self) -> Optional[Path]:
        current = self.project_path
        while current != current.parent:
            if (current / "CONTRIBUTING.md").exists() and (current / "template").exists():
                return current
            if (current / ".git").exists():
                return current
            current = current.parent
        return None

    def _determine_category_and_slug(self) -> tuple[str, str]:
        slug = self.project_path.name
        parent_name = self.project_path.parent.name
        if parent_name in ("agents", "tools"):
            return parent_name, slug

        if self.repo_root:
            try:
                rel = self.project_path.relative_to(self.repo_root)
                parts = rel.parts
                if len(parts) == 2 and parts[0] in ("agents", "tools"):
                    return parts[0], parts[1]
                # If path is deeper (e.g. inside tests/fixtures/good-tool)
                if "agents" in parts or "agent" in slug.lower():
                    return "agents", slug
                return "tools", slug
            except ValueError:
                pass

        category = "agents" if "agent" in slug.lower() else ("tools" if parent_name == "tools" else parent_name)
        return category, slug

    def _load_rules_config(self) -> dict[str, Any]:
        candidate_paths = [
            self.project_path / "rules.toml",
            Path(__file__).resolve().parent.parent / "rules.toml",
        ]
        if self.repo_root:
            candidate_paths.append(self.repo_root / "tools" / "merge-ready" / "rules.toml")

        for path in candidate_paths:
            if path.exists() and path.is_file():
                try:
                    with open(path, "rb") as f:
                        data = tomllib.load(f)
                        if not isinstance(data, dict):
                            self.config_errors.append(f"Invalid format in '{path}': root must be a table.")
                            continue
                        if "rules" in data:
                            if not isinstance(data["rules"], dict):
                                self.config_errors.append(f"Invalid format in '{path}': [rules] must be a table.")
                                continue
                            return data.get("rules", {})
                except Exception as e:
                    self.config_errors.append(f"Syntax error in configuration file '{path}': {e}")
        return {}

    def _load_template_readme(self) -> str:
        if self.base_ref and self.repo_root:
            try:
                out = subprocess.run(
                    ["git", "show", f"{self.base_ref}:template/README.md"],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                if out:
                    return out
            except Exception:
                pass

        if self.repo_root:
            template_path = self.repo_root / "template" / "README.md"
            if template_path.exists():
                try:
                    return template_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        return FALLBACK_TEMPLATE_README

    def _load_template_env(self) -> str:
        if self.base_ref and self.repo_root:
            try:
                out = subprocess.run(
                    ["git", "show", f"{self.base_ref}:template/.env.example"],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                if out:
                    return out
            except Exception:
                pass

        if self.repo_root:
            template_path = self.repo_root / "template" / ".env.example"
            if template_path.exists():
                try:
                    return template_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        return FALLBACK_TEMPLATE_ENV

    def _collect_files(self) -> list[Path]:
        collected: list[Path] = []
        # Standard system & virtual environment directories that are never part of source code:
        ignored_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for f in files:
                full_path = Path(root) / f
                rel_path = full_path.relative_to(self.project_path)
                posix_str = rel_path.as_posix()

                if full_path.is_symlink():
                    try:
                        resolved = full_path.resolve()
                        try:
                            resolved.relative_to(self.project_path.resolve())
                        except ValueError:
                            self.rejected_symlinks.append((posix_str, str(resolved)))
                            continue
                    except Exception as e:
                        self.unreadable_files.append((posix_str, str(e)))
                        continue

                try:
                    stat_res = full_path.stat()
                    if stat_res.st_size > MAX_FILE_SIZE:
                        self.oversized_files.append((posix_str, stat_res.st_size))
                        continue
                except Exception as e:
                    self.unreadable_files.append((posix_str, str(e)))
                    continue

                if len(collected) >= MAX_FILE_COUNT:
                    self.limit_exceeded_file_count = True
                    break

                collected.append(rel_path)

            if self.limit_exceeded_file_count:
                break

        return sorted(collected)

    def _collect_tracked_files(self) -> set[str]:
        if not self.repo_root:
            return {p.as_posix() for p in self.files}

        try:
            rel_proj = self.project_path.relative_to(self.repo_root).as_posix()
            res = subprocess.run(
                ["git", "ls-files", rel_proj],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=True,
            )
            tracked = set()
            for line in res.stdout.splitlines():
                line = line.strip()
                if line:
                    rel_to_proj = line[len(rel_proj) + 1 :] if line.startswith(rel_proj + "/") else line
                    tracked.add(rel_to_proj)
            return tracked
        except Exception:
            return {p.as_posix() for p in self.files}

    def read_text(self, rel_path: Path | str) -> Optional[str]:
        full = self.project_path / rel_path
        if not full.exists() or not full.is_file():
            return None
        try:
            if full.stat().st_size > MAX_FILE_SIZE:
                return None
            return full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

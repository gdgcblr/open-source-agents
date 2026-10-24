"""Tests for CLI check subcommand and report renderers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from contrib_audit.cli import main
from contrib_audit.models import AuditResult, Finding, Severity, Verdict
from contrib_audit.report import render_json, render_markdown, render_text


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    tpl = tmp_path / "template"
    tpl.mkdir()
    (tpl / "README.md").write_text(
        "# [Project Name]\n\n## Overview\n\n### Problem Statement & Intended Users\n\n"
        "## Technical Stack\n\n## Architecture & Data Flow\n\n## Prerequisites\n\n"
        "## Installation & Setup\n\n## Configuration & Environment Variables\n\n"
        "## How to Run\n\n## Example Input & Output\n\n## How to Test\n\n"
        "## Known Limitations\n\n## Security & Privacy Considerations\n\n"
        "## Future Improvements\n\n## License\n"
    )
    (tmp_path / "agents").mkdir()
    return tmp_path, tmp_path / "agents"


def make_valid_project(agents_dir: Path, slug: str = "my-cool-agent") -> Path:
    proj = agents_dir / slug
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "README.md").write_text(
        "# My Cool Agent\n\n> Does something awesome.\n\n"
        "## Overview\n\n### Problem Statement & Intended Users\n"
        "- **Problem**: Solves X.\n- **Intended Users**: Developers.\n\n"
        "## Technical Stack\n\n- Python 3.11+\n\n"
        "## Architecture & Data Flow\n\nInput -> Output\n\n"
        "## Prerequisites\n\n- Python 3.10+\n\n"
        "## Installation & Setup\n\n1. pip install\n\n"
        "## Configuration & Environment Variables\n\n"
        "| Variable Name | Required | Default | Description |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| `GOOGLE_API_KEY` | Yes | *None* | Key |\n"
        "| `MODEL_NAME` | No | `gemini-2.5-flash` | Model |\n\n"
        "## How to Run\n\n```bash\npython -m cool\n```\n\n"
        "## Example Input & Output\n\n### Example Input\n```\ncheck .\n```\n\n"
        "### Example Output\n```\nVerdict: READY\n```\n\n"
        "## How to Test\n\n```bash\npytest\n```\n\n"
        "## Known Limitations\n\nSome.\n\n"
        "## Security & Privacy Considerations\n\nLoaded from .env.\n\n"
        "## Future Improvements\n\n- [ ] Caching.\n\n"
        "## License\n\nMIT\n"
    )
    (proj / ".env.example").write_text(
        "GOOGLE_API_KEY=your_google_api_key_here\nMODEL_NAME=gemini-2.5-flash\n"
    )
    (proj / ".gitignore").write_text(".env\n.venv/\nvenv/\n")
    (proj / "requirements.txt").write_text("google-adk>=1.0\npython-dotenv>=1.0\n")
    return proj


class TestCLICheck:
    def test_valid_project_exits_0(self, tmp_path, capsys):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        rc = main(["check", str(proj), "--repo-root", str(repo)])
        assert rc == 0

    def test_missing_readme_exits_1(self, tmp_path, capsys):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        (proj / "README.md").unlink()
        rc = main(["check", str(proj), "--repo-root", str(repo)])
        assert rc == 1

    def test_json_format(self, tmp_path, capsys):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        main(["check", str(proj), "--repo-root", str(repo), "--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "verdict" in data
        assert "findings" in data

    def test_markdown_format(self, tmp_path, capsys):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        main(["check", str(proj), "--repo-root", str(repo), "--format", "markdown"])
        captured = capsys.readouterr()
        assert "# Contribution Review" in captured.out

    def test_nonexistent_path_exits_2(self, tmp_path):
        rc = main(["check", str(tmp_path / "does-not-exist")])
        assert rc == 2


class TestRenderers:
    def _make_result(self) -> AuditResult:
        result = AuditResult(project_path=Path("/tmp/test"), project_name="test")
        result.findings.append(
            Finding(
                rule_id="R04",
                severity=Severity.ERROR,
                file=Path("README.md"),
                line=None,
                message="Missing file",
                evidence=None,
                fix_hint="Add it.",
            )
        )
        return result

    def test_text_render(self):
        result = self._make_result()
        out = render_text(result, use_colour=False)
        assert "R04" in out
        assert "CHANGES_REQUESTED" in out

    def test_markdown_render(self):
        result = self._make_result()
        out = render_markdown(result)
        assert "R04" in out
        assert "CHANGES REQUESTED" in out

    def test_json_render(self):
        result = self._make_result()
        out = render_json(result)
        data = json.loads(out)
        assert data["verdict"] == "CHANGES_REQUESTED"
        assert len(data["findings"]) == 1

    def test_ready_verdict_text(self):
        result = AuditResult(project_path=Path("/tmp/x"), project_name="x")
        out = render_text(result, use_colour=False)
        assert "READY" in out

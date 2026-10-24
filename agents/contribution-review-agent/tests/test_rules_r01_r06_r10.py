"""Tests for R01-R06, R10: structure, naming, required files, README, env sync."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from contrib_audit.rules import run_all
from contrib_audit.rules.structure import check_location, check_naming, check_required_files
from contrib_audit.rules.readme import check_headings, check_env_sync, check_example_section
from contrib_audit.models import Severity, Verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal repo skeleton and return (repo_root, agents_dir)."""
    # template/README.md triggers auto-detection
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
    """Create a minimal valid project under agents/<slug>/."""
    proj = agents_dir / slug
    proj.mkdir(parents=True, exist_ok=True)

    (proj / "README.md").write_text(
        "# My Cool Agent\n\n> Does something awesome.\n\n"
        "## Overview\n\n### Problem Statement & Intended Users\n"
        "- **Problem**: Solves X.\n- **Intended Users**: Developers.\n\n"
        "## Technical Stack\n\n- **Language & Runtime**: Python 3.11+\n\n"
        "## Architecture & Data Flow\n\nInput -> Agent -> Output\n\n"
        "## Prerequisites\n\n- Python 3.10+\n\n"
        "## Installation & Setup\n\n1. `pip install -r requirements.txt`\n\n"
        "## Configuration & Environment Variables\n\n"
        "| Variable Name | Required | Default | Description |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| `GOOGLE_API_KEY` | Yes | *None* | Gemini API key |\n"
        "| `MODEL_NAME` | No | `gemini-2.5-flash` | Model |\n\n"
        "## How to Run\n\n```bash\npython -m my_agent\n```\n\n"
        "## Example Input & Output\n\n"
        "### Example Input\n```\ncheck agents/my-cool-agent\n```\n\n"
        "### Example Output\n```\nVerdict: READY\n```\n\n"
        "## How to Test\n\n```bash\npytest\n```\n\n"
        "## Known Limitations\n\nRate limits may apply.\n\n"
        "## Security & Privacy Considerations\n\nKeys loaded from .env.\n\n"
        "## Future Improvements\n\n- [ ] Add caching.\n\n"
        "## License\n\nMIT\n"
    )
    (proj / ".env.example").write_text(
        "GOOGLE_API_KEY=your_google_api_key_here\n"
        "MODEL_NAME=gemini-2.5-flash\n"
    )
    (proj / ".gitignore").write_text(".env\n.venv/\nvenv/\n")
    (proj / "requirements.txt").write_text("google-adk>=1.3.0\npython-dotenv>=1.0.0\n")

    return proj


# ---------------------------------------------------------------------------
# R01
# ---------------------------------------------------------------------------

class TestR01:
    def test_valid_location(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        findings = check_location(proj, repo)
        assert not any(f.rule_id == "R01" for f in findings)

    def test_invalid_location_tools_nested(self, tmp_path):
        repo, _ = make_repo(tmp_path)
        nested = repo / "agents" / "sub" / "deep-agent"
        nested.mkdir(parents=True)
        findings = check_location(nested, repo)
        assert any(f.rule_id == "R01" and f.severity == Severity.ERROR for f in findings)

    def test_invalid_location_root(self, tmp_path):
        repo, _ = make_repo(tmp_path)
        proj = repo / "some-agent"
        proj.mkdir()
        findings = check_location(proj, repo)
        assert any(f.rule_id == "R01" and f.severity == Severity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# R02 + R03
# ---------------------------------------------------------------------------

class TestR02R03:
    def test_valid_name(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents, "cool-agent-v2")
        findings = check_naming(proj)
        assert not findings

    def test_uppercase(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = agents / "CoolAgent"
        proj.mkdir()
        findings = check_naming(proj)
        assert any(f.rule_id == "R02" for f in findings)

    def test_underscore(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = agents / "cool_agent"
        proj.mkdir()
        findings = check_naming(proj)
        assert any(f.rule_id == "R02" for f in findings)

    def test_generic_name_demo(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = agents / "demo"
        proj.mkdir()
        findings = check_naming(proj)
        assert any(f.rule_id == "R03" for f in findings)

    def test_generic_name_test(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = agents / "test"
        proj.mkdir()
        findings = check_naming(proj)
        assert any(f.rule_id == "R03" for f in findings)


# ---------------------------------------------------------------------------
# R04
# ---------------------------------------------------------------------------

class TestR04:
    def test_all_present(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        findings = check_required_files(proj)
        assert not findings

    def test_missing_readme(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        (proj / "README.md").unlink()
        findings = check_required_files(proj)
        assert any(f.rule_id == "R04" and "README.md" in f.message for f in findings)

    def test_missing_manifest(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        (proj / "requirements.txt").unlink()
        findings = check_required_files(proj)
        assert any(f.rule_id == "R04" and "manifest" in f.message for f in findings)

    def test_accepts_pyproject(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        (proj / "requirements.txt").unlink()
        (proj / "pyproject.toml").write_text("[project]\nname='x'\n")
        findings = check_required_files(proj)
        assert not any(f.rule_id == "R04" and "manifest" in f.message for f in findings)


# ---------------------------------------------------------------------------
# R05
# ---------------------------------------------------------------------------

class TestR05:
    def test_all_headings_present(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        findings = check_headings(proj, repo)
        r05 = [f for f in findings if f.rule_id == "R05" and f.severity == Severity.ERROR]
        assert not r05, r05

    def test_missing_heading(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        text = (proj / "README.md").read_text()
        # Remove "## Known Limitations"
        text = text.replace("## Known Limitations\n\nRate limits may apply.\n\n", "")
        (proj / "README.md").write_text(text)
        findings = check_headings(proj, repo)
        assert any(f.rule_id == "R05" and "Known Limitations" in f.message for f in findings)

    def test_placeholder_warning(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        text = (proj / "README.md").read_text()
        (proj / "README.md").write_text(text + "\n[Project Name] is a placeholder\n")
        findings = check_headings(proj, repo)
        assert any(f.rule_id == "R05" and f.severity == Severity.WARNING for f in findings)


# ---------------------------------------------------------------------------
# R06
# ---------------------------------------------------------------------------

class TestR06:
    def test_in_sync(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        findings = check_env_sync(proj)
        assert not findings, findings

    def test_var_in_env_not_readme(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        with open(proj / ".env.example", "a") as f:
            f.write("EXTRA_SECRET=your_extra_key_here\n")
        findings = check_env_sync(proj)
        assert any(f.rule_id == "R06" and "EXTRA_SECRET" in f.message for f in findings)

    def test_var_in_readme_not_env(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        text = (proj / "README.md").read_text()
        text = text.replace(
            "| `MODEL_NAME` | No | `gemini-2.5-flash` | Model |\n",
            "| `MODEL_NAME` | No | `gemini-2.5-flash` | Model |\n"
            "| `UNDECLARED_VAR` | No | `` | Undeclared |\n",
        )
        (proj / "README.md").write_text(text)
        findings = check_env_sync(proj)
        assert any(f.rule_id == "R06" and "UNDECLARED_VAR" in f.message for f in findings)


# ---------------------------------------------------------------------------
# R10
# ---------------------------------------------------------------------------

class TestR10:
    def test_clean(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        findings = check_example_section(proj)
        assert not findings

    def test_template_text(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        text = (proj / "README.md").read_text()
        (proj / "README.md").write_text(text + "\nAnalysis completed:\n- agents/\n")
        findings = check_example_section(proj)
        assert any(f.rule_id == "R10" for f in findings)


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_ready(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        result = run_all(proj, repo, git_available=False)
        # Scope skip is INFO, should still be READY or APPROVE_WITH_NITS
        assert result.verdict in (Verdict.READY, Verdict.APPROVE_WITH_NITS)

    def test_r07_causes_reject(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        # Plant a fake secret built at runtime (never a real key)
        fake_key = "AIza" + "A" * 35   # matches Google API key pattern
        (proj / "oops.py").write_text(f'key = "{fake_key}"\n')
        result = run_all(proj, repo, git_available=False)
        assert result.verdict == Verdict.REJECT

    def test_missing_file_causes_changes_requested(self, tmp_path):
        repo, agents = make_repo(tmp_path)
        proj = make_valid_project(agents)
        (proj / ".env.example").unlink()
        result = run_all(proj, repo, git_available=False)
        assert result.verdict == Verdict.CHANGES_REQUESTED

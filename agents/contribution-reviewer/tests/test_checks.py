import shutil
import subprocess
from pathlib import Path

import pytest

from contribution_reviewer import checks

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_README = PROJECT_ROOT.parents[1] / "template" / "README.md"

GOOD_README = "# Weather Agent\n\n" + "\n\n".join(
    f"## {section}\n\nReal content for {section}." for section in checks.REQUIRED_README_SECTIONS
)


def make_project(root: Path, name: str = "weather-agent", parent: str = "agents", **files: str) -> Path:
    project = root / parent / name
    project.mkdir(parents=True)
    defaults = {
        "README.md": GOOD_README,
        ".gitignore": ".env\n.venv/\n",
        ".env.example": "GOOGLE_API_KEY=your_key_here\n",
        "requirements.txt": "google-adk\n",
    }
    for rel, content in {**defaults, **files}.items():
        if content is None:
            continue
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return project


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def init_repo(root: Path) -> None:
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# repo\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")


def test_well_formed_project_passes_all_checks(tmp_path):
    project = make_project(tmp_path)
    assert all(r["passed"] for r in checks.run_all_checks(str(project)))


@pytest.mark.parametrize("name", ["WeatherAgent", "weather_agent", "my-agent"])
def test_bad_folder_names_fail(tmp_path, name):
    project = make_project(tmp_path, name=name)
    assert not checks.check_structure(str(project))["passed"]


def test_wrong_parent_and_missing_files_fail(tmp_path):
    project = make_project(tmp_path, parent="examples", **{".env.example": None, "requirements.txt": None})
    issues = " ".join(checks.check_structure(str(project))["issues"])
    assert "agents/ or tools/" in issues
    assert ".env.example" in issues
    assert "manifest" in issues


def test_template_copy_is_flagged(tmp_path):
    project = make_project(tmp_path, **{"README.md": TEMPLATE_README.read_text(encoding="utf-8")})
    result = checks.check_readme(str(project))
    assert not result["passed"]
    assert result["details"]["placeholders"]
    assert not result["details"]["missing_sections"]


def test_placeholders_quoted_in_code_blocks_are_ignored(tmp_path):
    readme = GOOD_README + '\n\n```\nTemplate placeholder not replaced: "[Project Name]"\n```\n'
    project = make_project(tmp_path, **{"README.md": readme})
    assert checks.check_readme(str(project))["passed"]


def test_missing_sections_are_reported(tmp_path):
    project = make_project(tmp_path, **{"README.md": "# Thing\n\n## Overview\n\nHello"})
    missing = checks.check_readme(str(project))["details"]["missing_sections"]
    assert "How to Run" in missing and "Overview" not in missing


def test_secrets_are_detected_and_redacted(tmp_path):
    fake_key = "AIza" + "B" * 35
    project = make_project(tmp_path, **{"main.py": f'KEY = "{fake_key}"\n', ".env": "X=1\n"})
    result = checks.scan_secrets(str(project))
    text = " ".join(result["issues"])
    assert not result["passed"]
    assert "Google API key in main.py:1" in text
    assert ".env" in text
    assert fake_key not in text


def test_gitignored_files_are_not_scanned(tmp_path):
    init_repo(tmp_path)
    fake_key = "AIza" + "C" * 35
    project = make_project(tmp_path, **{".env": f"GOOGLE_API_KEY={fake_key}\n", ".venv/lib/x.py": "x = 1\n"})
    assert checks.scan_secrets(str(project))["passed"]


def test_scope_flags_changes_outside_project(tmp_path):
    init_repo(tmp_path)
    git(tmp_path, "branch", "base")
    project = make_project(tmp_path)
    (tmp_path / "agents" / "README.md").write_text("index\n", encoding="utf-8")
    assert checks.check_scope(str(project), base_ref="base")["passed"]

    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    result = checks.check_scope(str(project), base_ref="base")
    assert result["issues"] == ["Change outside the project folder: README.md"]


def test_scope_skips_unknown_base_ref(tmp_path):
    init_repo(tmp_path)
    project = make_project(tmp_path)
    result = checks.check_scope(str(project), base_ref="does-not-exist")
    assert result["passed"] and "skipped" in result["details"]


def test_missing_project_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        checks.check_structure(str(tmp_path / "nope"))


def test_reviews_itself_cleanly():
    """This project must pass its own checks (scope is checked in CI-free mode)."""
    for result in checks.run_all_checks(str(PROJECT_ROOT))[:3]:
        assert result["passed"], result

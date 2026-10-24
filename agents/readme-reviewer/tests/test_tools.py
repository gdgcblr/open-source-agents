from review_core.analysis.tools import (
    REQUIRED_SECTIONS,
    check_folder_name,
    check_manifest,
    check_readme_sections,
    list_project_files,
    scan_for_secrets,
)

FULL_README = "# Demo\n" + "".join(f"## {s.title()}\n" for s in REQUIRED_SECTIONS)


def make_project(tmp_path, name="good-agent", readme=FULL_README):
    root = tmp_path / name
    root.mkdir()
    (root / "README.md").write_text(readme)
    (root / "requirements.txt").write_text("requests\n")
    (root / ".env.example").write_text("API_KEY=your_key_here\n")
    (root / ".gitignore").write_text(".env\n")
    return root


def test_good_project_passes(tmp_path):
    root = make_project(tmp_path)
    assert check_readme_sections(str(root))["missing_sections"] == []
    assert check_manifest(str(root))["has_manifest"]
    assert scan_for_secrets(str(root))["clean"]
    assert check_folder_name(str(root))["is_kebab_case"]


def test_missing_sections_and_placeholder(tmp_path):
    root = make_project(tmp_path, readme="# [Project Name]\n## Overview\n")
    result = check_readme_sections(str(root))
    assert "known limitations" in result["missing_sections"]
    assert "overview" not in result["missing_sections"]
    assert result["placeholders_left"] == ["[Project Name]"]


def test_placeholders_quoted_in_code_are_ignored(tmp_path):
    readme = FULL_README + "Flags `[Project Name]` here.\n```\n[Project Name]\n```\n"
    root = make_project(tmp_path, readme=readme)
    assert check_readme_sections(str(root))["placeholders_left"] == []


def test_missing_readme(tmp_path):
    root = tmp_path / "empty-agent"
    root.mkdir()
    assert check_readme_sections(str(root))["has_readme"] is False
    assert not check_manifest(str(root))["has_manifest"]


def test_secret_and_env_file_flagged_and_redacted(tmp_path):
    root = make_project(tmp_path)
    fake = "AIza" + "A" * 35
    (root / "main.py").write_text(f'KEY = "{fake}"\n')
    (root / ".env").write_text("X=1\n")
    result = scan_for_secrets(str(root))
    assert not result["clean"]
    assert any(f["file"] == "main.py" for f in result["findings"])
    assert any(f["file"] == ".env" for f in result["findings"])
    assert fake not in str(result)


def test_nvidia_key_flagged(tmp_path):
    root = make_project(tmp_path)
    (root / "x.py").write_text('k = "nvapi-' + "a" * 30 + '"\n')
    assert any("NVIDIA" in f["issue"] for f in scan_for_secrets(str(root))["findings"])


def test_venv_flagged_but_not_listed(tmp_path):
    root = make_project(tmp_path)
    (root / ".venv").mkdir()
    (root / ".venv" / "lib.py").write_text("x = 1\n")
    assert any("Virtual environment" in f["issue"] for f in scan_for_secrets(str(root))["findings"])
    assert ".venv/lib.py" not in list_project_files(str(root))["files"]


def test_folder_name_rules(tmp_path):
    bad = tmp_path / "My_Agent"
    bad.mkdir()
    generic = tmp_path / "demo"
    generic.mkdir()
    assert not check_folder_name(str(bad))["is_kebab_case"]
    assert check_folder_name(str(generic))["is_generic"]


def test_bad_path_returns_error():
    assert "error" in check_manifest("/nonexistent/path/xyz")

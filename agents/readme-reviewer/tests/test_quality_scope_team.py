import subprocess

from review_core.analysis.tools import check_pr_scope, check_readme_quality

GOOD = """# Demo
## Overview
This project reviews documentation folders and reports problems clearly.
## How to Run
```bash
python main.py
pip install -r requirements.txt
cp .env.example .env
```
## Known Limitations
TBD
"""


def make_project(tmp_path, readme=GOOD, files=("main.py", "requirements.txt", ".env.example")):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "README.md").write_text(readme)
    for f in files:
        (proj / f).write_text("x")
    return proj


# ---- readme quality --------------------------------------------------------- #
def test_thin_section_detected_but_code_section_ok(tmp_path):
    result = check_readme_quality(str(make_project(tmp_path)))
    assert result["thin_sections"] == ["known limitations"]
    assert result["missing_referenced_files"] == []


def test_missing_referenced_files(tmp_path):
    proj = make_project(tmp_path, files=("requirements.txt",))
    assert check_readme_quality(str(proj))["missing_referenced_files"] == [".env.example", "main.py"]


def test_parent_section_includes_subsections(tmp_path):
    readme = "## Overview\n### Problem\nThis project reviews documentation folders and reports problems.\n"
    proj = make_project(tmp_path, readme=readme)
    assert check_readme_quality(str(proj))["thin_sections"] == []


def test_placeholder_and_flag_args_ignored(tmp_path):
    readme = "## How to Run\n```bash\ncd agents/<slug>\npython main.py --query x\npython -m pytest\n```\n"
    proj = make_project(tmp_path, readme=readme, files=("main.py",))
    assert check_readme_quality(str(proj))["missing_referenced_files"] == []


def test_quality_without_readme(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    assert check_readme_quality(str(proj))["has_readme"] is False


# ---- PR scope (real temporary git repo) ------------------------------------ #
def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


def make_repo(tmp_path):
    git(tmp_path, "init", "-b", "main")
    (tmp_path / "README.md").write_text("root")
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "README.md").write_text("| Agent |\n| --- |\n| *(None yet)* |\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "init")
    git(tmp_path, "checkout", "-b", "feat/x")
    proj = tmp_path / "agents" / "my-agent"
    proj.mkdir()
    (proj / "README.md").write_text("new")
    return proj


def test_scope_clean_with_one_index_row(tmp_path):
    proj = make_repo(tmp_path)
    (tmp_path / "agents" / "README.md").write_text("| Agent |\n| --- |\n| my-agent |\n")
    result = check_pr_scope(str(proj))
    assert result["applicable"] and result["within_scope"]
    assert result["index_rows_added"] == 1
    assert result["in_agents_or_tools"] and result["files_outside_project"] == []
    assert result["project_files_changed"] == 1


def test_scope_flags_outside_changes_and_extra_rows(tmp_path):
    proj = make_repo(tmp_path)
    (tmp_path / "README.md").write_text("changed root")
    (tmp_path / "agents" / "README.md").write_text("| Agent |\n| --- |\n| one |\n| two |\n")
    result = check_pr_scope(str(proj))
    assert not result["within_scope"]
    assert result["files_outside_project"] == ["README.md"]
    assert result["index_rows_added"] == 2


def test_scope_not_a_git_repo(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    result = check_pr_scope(str(proj))
    assert result["applicable"] is False


def test_scope_rejects_unsafe_base_ref(tmp_path, monkeypatch):
    proj = make_repo(tmp_path)
    monkeypatch.setenv("BASE_REF", "--output=/tmp/x")
    assert check_pr_scope(str(proj))["base"] == "main"


# ---- git-ignored local files are not blockers ------------------------------- #
def test_ignored_env_and_venv_are_not_findings(tmp_path):
    from review_core.analysis.tools import scan_for_secrets

    git(tmp_path, "init", "-b", "main")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".gitignore").write_text(".env\n.venv/\n")
    (proj / ".env").write_text("X=1\n")
    (proj / ".venv").mkdir()
    result = scan_for_secrets(str(proj))
    assert result["clean"] and result["findings"] == []
    assert {f["file"] for f in result["ignored_local_files"]} == {".env", ".venv"}


def test_unignored_env_is_still_a_finding(tmp_path):
    from review_core.analysis.tools import scan_for_secrets

    git(tmp_path, "init", "-b", "main")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text("X=1\n")
    result = scan_for_secrets(str(proj))
    assert not result["clean"]
    assert result["findings"][0]["file"] == ".env"

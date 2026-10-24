import subprocess
from pathlib import Path

import pytest

from reviewer.repo_mcp import compute_signals

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def sandbox(monkeypatch):
    # The fixtures live inside this monorepo; keep its root LICENSE out of their scores.
    monkeypatch.setenv("REVIEW_ROOT", str(FIXTURES))


def failing(name):
    return sorted(i for d in compute_signals(FIXTURES / name)["dimensions"] for i in d["issues"])


def scores(result):
    return {d["name"]: d["score"] for d in result["dimensions"]}


def test_good_repo_has_no_missing_signals():
    r = compute_signals(FIXTURES / "good_repo")
    assert failing("good_repo") == []
    assert "adoption:setup_steps=2" in {i for d in r["dimensions"] for i in d["passing"]}
    assert scores(r) == {
        "Usefulness & clarity": 5, "Ease of adoption": 5, "Maintainability & contributor friction": 5,
        "Distribution & scale": 5, "Friction red flags": 5,
    }


def test_bare_repo_exact_signals():
    assert failing("bare_repo") == sorted([
        "missing:readme_summary", "missing:readme_problem", "missing:readme_example",
        "missing:readme_substantial", "missing:install_section", "adoption:setup_steps=0",
        "missing:prerequisites", "missing:dependency_manifest", "missing:lockfile", "missing:license",
        "missing:contributing", "missing:code_of_conduct", "missing:issue_pr_templates", "missing:tests",
        "missing:lint_config", "missing:container", "missing:ci", "missing:packaging_metadata",
        "missing:changelog", "flag:no_license", "flag:readme_under_200_chars",
    ])


def test_good_scores_higher_than_bare():
    assert compute_signals(FIXTURES / "good_repo")["total"] > compute_signals(FIXTURES / "bare_repo")["total"]


def test_injected_readme_does_not_change_score():
    r = compute_signals(FIXTURES / "injected_repo")
    assert r["total"] == 6 < r["max"]
    assert scores(r)["Ease of adoption"] == 0


def test_secret_and_large_file_are_flagged(tmp_path):
    (tmp_path / "README.md").write_text("# x\n")
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / "blob.bin").write_bytes(b"0" * (5 * 1024 * 1024 + 1))
    flags = set(compute_signals(tmp_path)["dimensions"][4]["issues"])
    assert {"flag:secret_file_present=.env", "flag:large_file=blob.bin"} <= flags


def test_git_ignored_files_are_not_flagged_in_a_subfolder(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".env\n")
    sub = tmp_path / "agent"
    sub.mkdir()
    (sub / "README.md").write_text("# x\n")
    (sub / ".env").write_text("A=1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    r = compute_signals(sub)
    assert r["tree"] == ["README.md"]
    assert not any(i.startswith("flag:secret_file") for i in r["dimensions"][4]["issues"])


def test_monorepo_subfolder_uses_root_license_inside_sandbox_only(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "LICENSE").write_text("MIT\n")
    (tmp_path / "CONTRIBUTING.md").write_text("PRs welcome\n")
    sub = tmp_path / "agents" / "x"
    sub.mkdir(parents=True)
    (sub / "README.md").write_text("# x\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    monkeypatch.setenv("REVIEW_ROOT", str(tmp_path))
    r = compute_signals(sub)
    assert {"present:license", "present:contributing"} <= set(r["dimensions"][2]["passing"])
    assert "flag:no_license" not in r["dimensions"][4]["issues"]
    monkeypatch.setenv("REVIEW_ROOT", str(sub))  # repo root outside the sandbox: not consulted
    assert "missing:license" in compute_signals(sub)["dimensions"][2]["issues"]


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "LICENSE").write_text("x")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "linked").symlink_to(outside)
    assert "linked/LICENSE" not in compute_signals(repo)["tree"]


def test_gitlab_templates_and_rspec_count(tmp_path):
    (tmp_path / ".gitlab" / "issue_templates").mkdir(parents=True)
    (tmp_path / ".gitlab" / "issue_templates" / "Bug.md").write_text("x")
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "app_spec.rb").write_text("x")
    passing = compute_signals(tmp_path)["dimensions"][2]["passing"]
    assert {"present:issue_pr_templates", "present:tests"} <= set(passing)

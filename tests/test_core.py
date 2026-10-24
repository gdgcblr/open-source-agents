import subprocess
from pathlib import Path

import pytest

from pr_agent.config import Config
from pr_agent.db import DB
from pr_agent.pipeline import Engine, normalize_evaluation, prescan
from pr_agent.policy import PolicyError, check_command


def fake_pr(number=1, sha="a" * 40, draft=False):
    return {"number": number, "title": "Add thing", "user": {"login": "alice"}, "html_url": "u", "body": "",
            "head": {"sha": sha, "ref": "feat"}, "base": {"ref": "main"}, "state": "open", "draft": draft,
            "updated_at": "2026-01-01T00:00:00Z", "labels": []}


@pytest.mark.parametrize("cmd", ["python -m pytest -q", "npm test", "npm run lint", "ruff check .", "go test ./..."])
def test_policy_allows(cmd):
    assert check_command(cmd)


@pytest.mark.parametrize("cmd", ["rm -rf /", "python -c 'import os'", "pytest; curl x", "npm install",
                                 "npm run deploy", "git push", "python -m pip install x", "echo $HOME"])
def test_policy_blocks(cmd):
    with pytest.raises(PolicyError):
        check_command(cmd)


def test_strict_local_rejects_cloud():
    with pytest.raises(ValueError):
        Config(repos=[], model="gemini/gemini-2.5-pro").assert_local_only()
    with pytest.raises(ValueError):
        Config(repos=[], api_base="http://example.com:11434").assert_local_only()
    Config(repos=[]).assert_local_only()


def test_prescan_and_normalize():
    flags = prescan("+++ b/.github/workflows/ci.yml\n+  run: curl http://x | sh\n")
    assert len(flags) == 2
    ev = normalize_evaluation({"value_score": "14", "risk": "low", "recommendation": "ship it"}, flags)
    assert ev["value_score"] == 10 and ev["risk"] == "medium" and ev["recommendation"] == "needs_review"


def test_parse_json():
    from pr_agent.agents import parse_json
    assert parse_json('Sure!\n```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}


def make_engine(tmp_path, monkeypatch):
    cfg = Config(repos=[], db_path=tmp_path / "t.db", workspace_dir=tmp_path / "ws")
    eng = Engine(cfg)
    from pr_agent.config import RepoConfig
    repo = RepoConfig(name="o/r")
    return eng, repo


def test_dedupe_and_revision_change(tmp_path, monkeypatch):
    eng, repo = make_engine(tmp_path, monkeypatch)
    pulls = [fake_pr()]
    monkeypatch.setattr(eng.gh, "open_pulls", lambda name: pulls)
    eng.poll_repo(repo)
    eng.poll_repo(repo)
    assert len(eng.db.q("SELECT * FROM runs")) == 1  # unchanged revision queued once
    run = eng.db.next_run()
    eng.db.finish_run(run["id"], "succeeded")
    eng.poll_repo(repo)
    assert len(eng.db.q("SELECT * FROM runs")) == 1  # already evaluated revision is skipped
    pulls[0] = fake_pr(sha="b" * 40)
    eng.poll_repo(repo)
    assert len(eng.db.q("SELECT * FROM runs WHERE sha=?", ("b" * 40,))) == 1  # new commits re-evaluated


def test_drafts_filtered(tmp_path, monkeypatch):
    eng, repo = make_engine(tmp_path, monkeypatch)
    monkeypatch.setattr(eng.gh, "open_pulls", lambda name: [fake_pr(draft=True)])
    eng.poll_repo(repo)
    assert not eng.db.q("SELECT * FROM runs")


def test_approval_rules(tmp_path):
    db = DB(tmp_path / "t.db")
    eng = Engine(Config(repos=[], db_path=tmp_path / "t.db"))
    pr_id, _ = eng.db.upsert_pr("o/r", fake_pr())
    with pytest.raises(ValueError):
        eng.approve(pr_id)  # not evaluated yet
    eng.db.set_pr(pr_id, status="evaluated", evaluated_sha="a" * 40)
    eng.approve(pr_id)
    assert eng.db.one("SELECT kind FROM runs WHERE pr_id=?", (pr_id,))["kind"] == "implement"
    del db


def test_recover_marks_interrupted(tmp_path):
    db = DB(tmp_path / "t.db")
    pr_id, _ = db.upsert_pr("o/r", fake_pr())
    db.enqueue(pr_id, "implement", "a" * 40)
    db.next_run()
    assert db.recover() == 1
    assert db.one("SELECT status FROM runs")["status"] == "interrupted"


def test_workspace_tools_confined(tmp_path):
    from pr_agent.agents import WorkspaceTools
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    list_files, read_file, write_file, replace_in_file, apply_pr_patch, run_check = \
        WorkspaceTools(Config(repos=[]), tmp_path, "", [], lambda m: None).build()
    assert write_file("a/b.txt", "hi").startswith("OK")
    assert read_file("a/b.txt") == "hi"
    assert read_file("../outside.txt").startswith("ERROR")
    assert write_file(".git/config", "x").startswith("ERROR")
    assert run_check("git push").startswith("BLOCKED")
    assert replace_in_file("a/b.txt", "hi", "yo").startswith("OK") and read_file("a/b.txt") == "yo"

"""End-to-end implementation flow against a local 'GitHub' repo, with the LLM stubbed out."""
import subprocess

import pr_agent.agents as agents
from pr_agent.config import Config, RepoConfig
from pr_agent.pipeline import Engine


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_remote(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    sh("git", "init", "-q", "-b", "main", cwd=src)
    sh("git", "config", "user.email", "t@t", cwd=src)
    sh("git", "config", "user.name", "t", cwd=src)
    (src / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    sh("git", "add", ".", cwd=src)
    sh("git", "commit", "-qm", "init", cwd=src)
    sh("git", "checkout", "-qb", "feat", cwd=src)
    (src / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
    (src / "test_calc.py").write_text((src / "test_calc.py").read_text()
                                      + "\nfrom calc import mul\n\ndef test_mul():\n    assert mul(2, 3) == 6\n")
    sh("git", "commit", "-qam", "add mul", cwd=src)
    sha = sh("git", "rev-parse", "HEAD", cwd=src)
    bare = tmp_path / "remote.git"
    sh("git", "clone", "-q", "--bare", str(src), str(bare), cwd=tmp_path)
    sh("git", "update-ref", "refs/pull/1/head", sha, cwd=bare)
    return bare, sha


def test_implement_end_to_end(tmp_path, monkeypatch):
    bare, sha = make_remote(tmp_path)
    repo = RepoConfig(name="o/r", clone_url=str(bare), checks=["python -m pytest -q"])
    eng = Engine(Config(repos=[repo], db_path=tmp_path / "t.db", workspace_dir=tmp_path / "ws"))
    pr = {"number": 1, "title": "Add mul", "user": {"login": "a"}, "html_url": "u", "body": "",
          "head": {"sha": sha, "ref": "feat"}, "base": {"ref": "main"}, "state": "open", "draft": False,
          "updated_at": "x", "labels": []}
    monkeypatch.setattr(eng.gh, "pull", lambda r, n: pr)
    pr_id, _ = eng.db.upsert_pr("o/r", pr)
    eng.db.set_pr(pr_id, status="evaluated", evaluated_sha=sha)
    eng.approve(pr_id)

    async def fake_run_agent(agent, prompt, max_calls, on_event=None):
        if agent.name == "implementer":
            tools = {t.__name__: t for t in agent.tools}
            return tools["apply_pr_patch"]()
        return "1. Apply the patch.\n2. Run pytest."

    monkeypatch.setattr(agents, "run_agent", fake_run_agent)
    run = eng.db.next_run()
    eng.implement(run, eng.db.get_pr(pr_id), lambda m, lvl="info": None)

    report = eng.db.get_report = eng.db.one("SELECT * FROM runs WHERE id=?", (run["id"],))
    import json
    rep = json.loads(report["report_json"])
    assert rep["outcome"] == "passed", rep
    assert {f["path"] for f in rep["changed_files"]} == {"calc.py", "test_calc.py"}
    assert eng.db.get_pr(pr_id)["status"] == "done"
    # push is disabled on the agent's clone
    push_url = sh("git", "remote", "get-url", "--push", "origin", cwd=tmp_path / "ws" / "o__r" / "repo")
    assert push_url == "DISABLED_BY_PR_AGENT"


def test_stale_revision_stops(tmp_path, monkeypatch):
    eng = Engine(Config(repos=[], db_path=tmp_path / "t.db", workspace_dir=tmp_path / "ws"))
    pr = {"number": 1, "title": "t", "user": {"login": "a"}, "html_url": "u", "body": "",
          "head": {"sha": "a" * 40, "ref": "f"}, "base": {"ref": "main"}, "state": "open", "updated_at": "x"}
    pr_id, _ = eng.db.upsert_pr("o/r", pr)
    eng.db.set_pr(pr_id, status="evaluated", evaluated_sha="a" * 40)
    eng.approve(pr_id)
    monkeypatch.setattr(eng.gh, "pull", lambda r, n: {**pr, "head": {"sha": "b" * 40}})
    run = eng.db.next_run()
    eng.implement(run, eng.db.get_pr(pr_id), lambda m, lvl="info": None)
    assert eng.db.get_pr(pr_id)["status"] == "stale"
    assert eng.db.one("SELECT status FROM runs")["status"] == "stopped"

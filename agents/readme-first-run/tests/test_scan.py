import io
import json
import subprocess

import pytest

from firstrun import scan
from firstrun.models import Diagnosis, Report, Round, RunResult, Step, StepResult


def pr(number, files, *, owner="alice", repo="open-source-agents", ref="feat/thing", author="alice", head=True):
    return {
        "number": number,
        "title": f"feat: project {number}",
        "author": {"login": author},
        "headRefName": ref,
        "headRepository": {"id": "R1", "name": repo} if head else None,
        "headRepositoryOwner": {"id": "U1", "login": owner} if head else None,
        "files": [{"path": p, "additions": 1, "deletions": 0} for p in files],
        "url": f"https://github.com/gdgcblr/open-source-agents/pull/{number}",
    }


@pytest.fixture
def fake_gh(monkeypatch):
    calls = []
    state = {"returncode": 0, "stdout": "[]", "stderr": ""}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, state["returncode"], state["stdout"], state["stderr"])

    monkeypatch.setattr(scan.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(scan.subprocess, "run", fake_run)
    return state, calls


def test_project_folders_from_pr_files():
    files = [
        "agents/README.md",
        "README.md",
        "agents/pdf-qa/main.py",
        "agents/pdf-qa/README.md",
        "tools/mcp-search/server.py",
        "template/README.md",
        "agents/pdf-qa/src/x.py",
    ]
    assert scan.project_folders(files) == ["agents/pdf-qa", "tools/mcp-search"]
    assert scan.project_folders(files, ("tools",)) == ["tools/mcp-search"]


def test_tree_url():
    assert scan.tree_url("bob", "open-source-agents", "feat/x", "agents/y") == \
        "https://github.com/bob/open-source-agents/tree/feat/x/agents/y"


def test_discover_prs_builds_targets_and_skips(fake_gh):
    state, calls = fake_gh
    state["stdout"] = json.dumps([
        pr(7, ["agents/README.md"]),
        pr(3, ["agents/pdf-qa/main.py", "tools/mcp-search/server.py"], owner="bob", ref="feat/pdf"),
        pr(5, ["agents/gone/main.py"], head=False),
        pr(9, ["agents/readme-first-run/README.md"]),
    ])
    targets = scan.discover_prs("gdgcblr/open-source-agents")

    labels = [t.label for t in targets]
    assert labels == ["PR #3 agents/pdf-qa", "PR #3 tools/mcp-search", "PR #5 agents/gone",
                      "PR #7", "PR #9 agents/readme-first-run"]
    ok = [t for t in targets if not t.skip]
    assert [t.target for t in ok] == [
        "https://github.com/bob/open-source-agents/tree/feat/pdf/agents/pdf-qa",
        "https://github.com/bob/open-source-agents/tree/feat/pdf/tools/mcp-search",
    ]
    assert ok[0].author == "alice" and ok[0].pr == 3
    reasons = {t.label: t.skip for t in targets if t.skip}
    assert reasons["PR #5 agents/gone"] == "the head repository was deleted"
    assert "touches no" in reasons["PR #7"]
    assert "FirstRun itself" in reasons["PR #9 agents/readme-first-run"]
    # read-only: a single `gh pr list` call
    assert len(calls) == 1 and calls[0][:3] == ["gh", "pr", "list"]


def test_gh_missing(monkeypatch):
    monkeypatch.setattr(scan.shutil, "which", lambda name: None)
    with pytest.raises(scan.ScanError, match="not installed"):
        scan.discover_prs("a/b")


def test_gh_not_logged_in(fake_gh):
    state, _ = fake_gh
    state.update(returncode=1, stdout="", stderr="To get started with GitHub CLI, please run:  gh auth login")
    with pytest.raises(scan.ScanError, match="gh auth login"):
        scan.discover_prs("a/b")


def test_gh_other_failure_and_bad_json(fake_gh):
    state, _ = fake_gh
    state.update(returncode=1, stderr="GraphQL: Could not resolve to a Repository")
    with pytest.raises(scan.ScanError, match="Could not resolve"):
        scan.discover_prs("a/b")
    state.update(returncode=0, stdout="not json", stderr="")
    with pytest.raises(scan.ScanError, match="could not read"):
        scan.discover_prs("a/b")


def test_discover_local(tmp_path):
    for d in ["agents/alpha", "agents/readme-first-run", "agents/.hidden", "tools/beta"]:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "agents" / "README.md").write_text("index")
    targets = scan.discover_local(tmp_path)
    assert [(t.folder, bool(t.skip)) for t in targets] == [
        ("agents/alpha", False), ("agents/readme-first-run", True), ("tools/beta", False),
    ]
    assert targets[0].target == str((tmp_path / "agents" / "alpha").resolve())
    with pytest.raises(scan.ScanError):
        scan.discover_local(tmp_path / "missing")


def test_select_only_and_limit():
    ts = [scan.Target(f"agents/{n}", f"agents/{n}", f"/x/{n}") for n in "abcd"]
    ts.append(scan.Target("PR #1", "", "", skip="touches no project folder"))
    assert [t.folder for t in scan.select(ts, ["b", "agents/d"], None)] == ["agents/b", "agents/d", ""]
    assert [t.folder for t in scan.select(ts, [], 2)] == ["agents/a", "agents/b", ""]


def fake_report(verdict, *, failed_cmd=None, summary="", ttfs=None, error=None):
    results, doc = [], None
    if failed_cmd:
        results = [StepResult(Step(1, "pip install -r requirements.txt"), "passed", 0, "", 1.0),
                   StepResult(Step(2, failed_cmd), "failed", 1, "boom", 0.1)]
        doc = RunResult("as documented", "failed", results, 1.1, "docker python:3.12-slim", "")
    rounds = [Round(1, Diagnosis(category="missing_dependency", summary=summary))] if summary else []
    return Report(
        project="p", source="s", started_at="", finished_at="", verdict=verdict,
        headline=f"headline {verdict}", documented_plan=None, documented_run=doc, rounds=rounds,
        settings={"engine": "rules (offline)", "sandbox_detail": "docker python:3.12-slim"},
        metrics={"time_to_first_success": ttfs}, error=error,
    )


def test_run_scan_writes_scoreboard(tmp_path, monkeypatch):
    reports = {
        "/x/alpha": fake_report("fixed", failed_cmd="python main.py",
                                summary="main.py imports dotenv | not declared", ttfs=41.7),
        "/x/beta": fake_report("passed", ttfs=12.0),
        "/x/gamma": fake_report("blocked", failed_cmd="python app.py", summary="needs GEMINI_API_KEY"),
    }
    seen = []

    def fake_run_check(target, settings, *, subdir=None, on_event=None, run_dir=None):
        seen.append((target, run_dir))
        run_dir.mkdir(parents=True)
        (run_dir / "report.md").write_text("r")
        if target == "/x/boom":
            raise RuntimeError("kaboom")
        return reports[target], run_dir

    monkeypatch.setattr(scan.agent, "run_check", fake_run_check)
    targets = [
        scan.Target("PR #3 agents/alpha", "agents/alpha", "/x/alpha", author="alice", pr=3,
                    pr_url="https://github.com/o/r/pull/3"),
        scan.Target("agents/beta", "agents/beta", "/x/beta"),
        scan.Target("agents/gamma", "agents/gamma", "/x/gamma"),
        scan.Target("agents/boom", "agents/boom", "/x/boom"),
        scan.Target("PR #7", "", "", pr=7, pr_url="https://github.com/o/r/pull/7", title="docs", skip="touches no project folder"),
    ]
    settings = scan.Settings(sandbox="docker", offline=True, out_dir=tmp_path)
    stream = io.StringIO()
    scan_dir, rows = scan.run_scan(targets, settings, source="o/r open PRs", out=tmp_path, stream=stream)

    assert [r.verdict for r in rows] == ["fixed", "passed", "blocked", "error"]
    assert all(rd.parent == scan_dir / "runs" for _, rd in seen)
    progress = stream.getvalue().splitlines()
    assert progress[0].startswith("[1/4] PR #3 agents/alpha ... FIXED in") and progress[0].endswith("failed at step 2")
    assert "ERROR" in progress[3]

    md = (scan_dir / "scoreboard.md").read_text()
    assert md.startswith("# FirstRun scoreboard: o/r open PRs")
    assert "| PR / folder | Author | Verdict | Failed at step | Diagnosis | Time to first success | Report |" in md
    assert "[#3](https://github.com/o/r/pull/3) `agents/alpha` | @alice | FIXED | `2: python main.py`" in md
    assert "dotenv \\| not declared" in md  # pipes cannot break the table
    assert "| 42s | [report](runs/01-agents-alpha/report.md) |" in md
    assert "1 work as documented, 1 fixed by a verified patch, 1 blocked on credentials, 0 failed, 1 could not be checked" in md
    assert "FirstRun crashed: kaboom" in md
    assert "- [#7](https://github.com/o/r/pull/7) docs: touches no project folder" in md
    assert "\u2014" not in md

    data = json.loads((scan_dir / "scoreboard.json").read_text())
    assert data["counts"]["fixed"] == 1 and data["counts"]["error"] == 1
    assert data["rows"][0]["time_to_first_success"] == 41.7
    assert data["skipped"][0]["pr"] == 7
    assert "env_keys" in data["settings"]


def test_list_flag_runs_nothing(tmp_path, monkeypatch):
    (tmp_path / "agents" / "alpha").mkdir(parents=True)
    (tmp_path / "agents" / "readme-first-run").mkdir(parents=True)

    def boom(*a, **k):
        raise AssertionError("--list must not run checks")

    monkeypatch.setattr(scan.agent, "run_check", boom)
    out = io.StringIO()
    assert scan.main(["--root", str(tmp_path), "--list"], stream=out) == 0
    text = out.getvalue()
    assert "check  agents/alpha" in text
    assert "skip   agents/readme-first-run: FirstRun itself" in text
    assert "1 to check, 1 skipped" in text


def test_main_reports_scan_errors(monkeypatch, capsys):
    monkeypatch.setattr(scan.shutil, "which", lambda name: None)
    assert scan.main(["--prs", "a/b", "--list"]) == 3
    assert "not installed" in capsys.readouterr().err


def test_main_runs_local_scan(tmp_path, monkeypatch):
    (tmp_path / "agents" / "alpha").mkdir(parents=True)

    def fake_run_check(target, settings, *, subdir=None, on_event=None, run_dir=None):
        assert settings.offline and settings.sandbox == "local"
        run_dir.mkdir(parents=True)
        return fake_report("passed", ttfs=3.0), run_dir

    monkeypatch.setattr(scan.agent, "run_check", fake_run_check)
    out = io.StringIO()
    code = scan.main(["--root", str(tmp_path), "--offline", "--sandbox", "local", "--out", str(tmp_path / "o")], stream=out)
    assert code == 0
    assert "Scoreboard:" in out.getvalue()
    assert list((tmp_path / "o").glob("scan-*/scoreboard.md"))

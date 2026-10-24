import json
from pathlib import Path

import pytest

from firstrun import agent
from firstrun.models import Diagnosis, Edit, Plan, RunResult, Step, StepResult


class FakeSandbox:
    """Fails `python main.py` until requirements.txt mentions python-dotenv."""

    name = "fake"

    def __init__(self, needs_key=False):
        self.needs_key = needs_key
        self.runs = []

    def available(self):
        return True, ""

    def describe(self):
        return "fake sandbox"

    def run(self, project_dir, steps, *, env=None, label="as documented", on_event=None, timeout=900):
        self.runs.append((Path(project_dir), label))
        reqs = (Path(project_dir) / "requirements.txt").read_text()
        results = []
        status = "passed"
        for s in steps:
            if status != "passed":
                results.append(StepResult(s, "not_run", None, "", 0.0))
                continue
            if s.command == "python main.py" and self.needs_key and "GEMINI_API_KEY" not in (env or {}):
                results.append(StepResult(s, "failed", 1, "KeyError: 'GEMINI_API_KEY'", 0.1))
                status = "failed"
            elif s.command == "python main.py" and "python-dotenv" not in reqs:
                out = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'dotenv'"
                results.append(StepResult(s, "failed", 1, out, 0.1))
                status = "failed"
            else:
                results.append(StepResult(s, "passed", 0, "hello" if s.command == "python main.py" else "", 0.1))
        return RunResult(label, status, results, 0.3, "fake sandbox", "log for " + label)


def plan_for(project_dir):
    steps = [
        Step(1, "pip install -r requirements.txt", kind="setup", line=5),
        Step(2, "python main.py", kind="run", line=9),
    ]
    return Plan(steps=steps, readme_path="README.md", expected_output="hello")


def missing_dotenv(project_dir, plan, run):
    failed = run.failed_step
    if failed and "dotenv" in failed.output:
        return Diagnosis(
            category="missing_dependency",
            summary="main.py imports dotenv but requirements.txt does not declare python-dotenv.",
            edits=[Edit("requirements.txt", "", "python-dotenv\n")],
            confidence="high",
        )
    if failed and "KeyError" in failed.output:
        return Diagnosis(category="credentials_required", summary="needs a key", blocked=True,
                         missing_env=["GEMINI_API_KEY"])
    return None


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "demo-project"
    root.mkdir()
    (root / "README.md").write_text("# demo\n")
    (root / "requirements.txt").write_text("colorama\n")
    (root / "main.py").write_text("import dotenv\nprint('hello')\n")
    return root


@pytest.fixture
def wired(monkeypatch):
    box = FakeSandbox()
    monkeypatch.setattr(agent, "make_sandbox", lambda *a, **k: box)
    monkeypatch.setattr(agent, "extract_plan", plan_for)
    monkeypatch.setattr(agent.rules, "diagnose", missing_dotenv)
    monkeypatch.setattr(agent.rules, "static_hints", lambda p: [])
    monkeypatch.setattr(agent.rules, "detect_credentials", lambda out, p: None)
    monkeypatch.setattr(agent, "get_llm", lambda *a, **k: None)
    return box


def settings(tmp_path, **kw):
    return agent.Settings(sandbox="local", offline=True, out_dir=tmp_path / "runs", **kw)


def test_failed_as_documented_then_fix_verified(project, wired, tmp_path):
    events = []
    report, run_dir = agent.run_check(str(project), settings(tmp_path), on_event=lambda *e: events.append(e))

    assert report.verdict == "fixed"
    assert report.documented_run.status == "failed"
    assert report.documented_run.failed_step.step.index == 2
    assert "+python-dotenv" in report.final_diff
    assert report.rounds[0].verification.status == "passed"
    # the original project is never touched
    assert (project / "requirements.txt").read_text() == "colorama\n"
    # the verification ran on a different copy
    assert wired.runs[0][0] == project and wired.runs[1][0] != project
    assert (run_dir / "fix.patch").read_text() == report.final_diff
    data = json.loads((run_dir / "report.json").read_text())
    assert data["verdict"] == "fixed" and "log" not in data["documented_run"]
    assert (run_dir / "logs" / "as-documented.log").exists()
    stages = [e[2]["stage"] for e in events if e[0] == "stage" and e[2]["state"] == "start"]
    assert stages == ["understand", "attempt", "investigate", "repair", "verify", "report"]
    assert report.output_check["similarity"] == 1.0


def test_passes_as_documented(project, wired, tmp_path):
    (project / "requirements.txt").write_text("python-dotenv\n")
    report, run_dir = agent.run_check(str(project), settings(tmp_path))
    assert report.verdict == "passed"
    assert report.rounds == []
    assert not (run_dir / "fix.patch").exists()
    assert "Works as documented" in report.headline


def test_blocked_on_credentials(project, monkeypatch, wired, tmp_path):
    (project / "requirements.txt").write_text("python-dotenv\n")
    wired.needs_key = True
    report, _ = agent.run_check(str(project), settings(tmp_path))
    assert report.verdict == "blocked"
    assert "GEMINI_API_KEY" in report.headline
    assert len(wired.runs) == 1  # no fake fix attempt


def test_supplied_secret_unblocks_and_is_not_recorded(project, wired, tmp_path):
    (project / "requirements.txt").write_text("python-dotenv\n")
    wired.needs_key = True
    report, run_dir = agent.run_check(str(project), settings(tmp_path, env={"GEMINI_API_KEY": "sk-test-123"}))
    assert report.verdict == "passed"
    assert report.settings["env_keys"] == ["GEMINI_API_KEY"]
    for f in run_dir.rglob("*"):
        if f.is_file():
            assert "sk-test-123" not in f.read_text()


def test_no_repair_reports_diagnosis_only(project, wired, tmp_path):
    report, run_dir = agent.run_check(str(project), settings(tmp_path, repair=False))
    assert report.verdict == "failed"
    assert report.rounds[0].diagnosis.category == "missing_dependency"
    assert report.rounds[0].verification is None
    assert len(wired.runs) == 1


def test_stops_when_fix_does_not_change_failure(project, wired, monkeypatch, tmp_path):
    def useless(project_dir, plan, run):
        return Diagnosis(category="code_bug", summary="try a comment", edits=[Edit("main.py", "", "# hm\n")])

    monkeypatch.setattr(agent.rules, "diagnose", useless)
    report, _ = agent.run_check(str(project), settings(tmp_path, max_rounds=3))
    assert report.verdict == "failed"
    assert len(report.rounds) == 1
    assert "+# hm" in report.final_diff


def test_unknown_target_is_an_error(wired, tmp_path):
    report, run_dir = agent.run_check(str(tmp_path / "nope"), settings(tmp_path))
    assert report.verdict == "error"
    assert "neither a folder nor a GitHub URL" in report.error
    assert (run_dir / "report.md").exists()


def test_export_placeholder_skipped_when_secret_supplied():
    plan = Plan(steps=[Step(1, "export GEMINI_API_KEY=your_key_here"), Step(2, "python main.py")])
    out = agent._skip_supplied_secrets(plan, {"GEMINI_API_KEY": "x"})
    assert [s.command for s in out.steps] == ["python main.py"]
    assert out.steps[0].index == 1
    assert out.skipped[0].reason == "GEMINI_API_KEY supplied to FirstRun"


def _lint_run(tmp_path, output, *, last=True, code=1):
    root = tmp_path / "lint"
    root.mkdir()
    (root / "README.md").write_text(
        "# lint\n\n```bash\npip install .\n```\n\n```console\n$ python -m lint broken.json\n"
        "broken.json\n  error S001 missing items\n2 errors, 5 warnings\n```\n"
    )
    steps = [Step(1, "pip install .", line=4), Step(2, "python -m lint broken.json", kind="run", line=8)]
    if not last:
        steps.append(Step(3, "python -m pytest", kind="test", line=20))
    results = [StepResult(steps[0], "passed", 0, "", 0.1), StepResult(steps[1], "failed", code, output, 0.1)]
    results += [StepResult(s, "not_run", None, "", 0.0) for s in steps[2:]]
    plan = Plan(steps=steps, readme_path="README.md")
    return root, plan, RunResult("as documented", "failed", results, 0.2, "fake", "")


LINT_OUTPUT = "broken.json\n  error S001 missing items\n\n2 errors, 5 warnings, 1 info\n"


def test_last_step_exit_matching_documented_output_passes(tmp_path):
    root, plan, run = _lint_run(tmp_path, LINT_OUTPUT)
    events = []
    assert agent._accept_documented_exit(run, plan, root, lambda *e: events.append(e))
    assert run.status == "passed" and run.results[1].ok and run.results[1].exit_code == 1
    assert any("non-zero exit matches the documented example" in n for n in plan.notes)
    assert events and events[0][0] == "info"


@pytest.mark.parametrize("kw, output", [
    ({"last": False}, LINT_OUTPUT),
    ({"code": 3}, LINT_OUTPUT),
    ({}, "Traceback (most recent call last):\n" + LINT_OUTPUT),
    ({}, "Segmentation fault while loading the schema\n"),
])
def test_documented_exit_is_strict(tmp_path, kw, output):
    root, plan, run = _lint_run(tmp_path, output, **kw)
    assert not agent._accept_documented_exit(run, plan, root, lambda *e: None)
    assert run.status == "failed"


def test_blocked_headline_for_a_host_tool():
    from firstrun.models import Report, Round

    diag = Diagnosis(category="platform_issue", blocked=True,
                     summary="Needs docker inside the sandbox, which FirstRun does not provide.")
    report = Report(project="lab", source="lab", started_at="", finished_at="", verdict="blocked",
                    headline="", documented_plan=None, documented_run=None, rounds=[Round(1, diag)])
    headline = agent._headline(report)
    assert headline.startswith("Blocked: Needs docker inside the sandbox")
    assert "credentials" not in headline

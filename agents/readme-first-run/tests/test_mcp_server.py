import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters  # noqa: E402

from firstrun import mcp_server  # noqa: E402
from firstrun.models import Diagnosis, Edit, Evidence, Plan, Report, Round, RunResult, Step, StepResult  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def fake_report(verdict="fixed"):
    step = Step(2, "python main.py --day 3", kind="run", line=38)
    out = "\n".join(f"line {i}" for i in range(30)) + "\nModuleNotFoundError: No module named 'dotenv'"
    doc = RunResult("as documented", "failed", [
        StepResult(Step(1, "pip install -r requirements.txt", line=24), "passed", 0, "", 3.0),
        StepResult(step, "failed", 1, out, 0.2),
    ], 3.2, "fake", "")
    verify = RunResult("after fix 1", "passed", [StepResult(step, "passed", 0, "ok", 0.1)], 4.0, "fake", "")
    diag = Diagnosis(
        category="missing_dependency",
        summary="main.py imports dotenv but requirements.txt does not list python-dotenv.",
        evidence=[Evidence("main.py", 3, "imports dotenv"), Evidence("requirements.txt", None, "no python-dotenv")],
        edits=[Edit("requirements.txt", "", "python-dotenv\n")],
        confidence="high",
    )
    return Report(
        project="quote-of-the-day", source="examples/quote-of-the-day", started_at="t0", finished_at="t1",
        verdict=verdict, headline="As documented, setup fails at step 2.",
        documented_plan=Plan(steps=[step]), documented_run=doc,
        rounds=[Round(1, diag, diff="+python-dotenv\n", verification=verify)],
        final_diff="diff --git a/requirements.txt b/requirements.txt\n+python-dotenv\n",
        metrics={"time_to_first_success": 4.0, "fixes_applied": 1},
    )


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRSTRUN_RUNS_DIR", str(tmp_path / "runs"))
    return tmp_path / "runs"


@pytest.fixture
def fake_check(monkeypatch, runs):
    calls = []

    def run_check(target, settings, *, subdir=None, on_event=None, run_dir=None):
        calls.append((target, subdir, settings))
        on_event("stage", "understand start", {"stage": "understand", "state": "start"})
        on_event("warn", "no key, using rules", None)
        out = runs / "20261024-000000-quote-of-the-day"
        out.mkdir(parents=True)
        (out / "report.md").write_text("# FirstRun report: quote-of-the-day\n")
        return fake_report(), out

    monkeypatch.setattr(mcp_server.agent, "run_check", run_check)
    return calls


def test_plan_lists_steps_and_skips_without_running():
    result = mcp_server.plan_summary(str(EXAMPLES / "quote-of-the-day"), offline=True)
    commands = [s["command"] for s in result["steps"]]
    assert "python main.py --day 3" in commands
    assert any("Scripts" in s["command"] for s in result["skipped"])
    assert result["planner"] == "rules"
    assert any("dotenv" in h for h in result["static_hints"])


def test_plan_reports_bad_target():
    assert "error" in mcp_server.plan_summary("/definitely/not/here", offline=True)


def test_check_summary_is_compact(fake_check, runs):
    events = []
    result = mcp_server.run_and_summarize(
        "examples/quote-of-the-day", sandbox="local", offline=True, max_rounds=2,
        on_event=lambda *e: events.append(e),
    )
    assert result["verdict"] == "fixed" and result["fix_verified"] is True
    assert result["works_as_documented"] is False
    tail = result["failing_step"]["output_tail"].splitlines()
    assert len(tail) == 20 and tail[-1].endswith("No module named 'dotenv'")
    assert result["failing_step"]["readme_line"] == 38
    assert result["diagnoses"][0]["evidence"][0] == "main.py:3: imports dotenv"
    assert result["diagnoses"][0]["verification"] == "passed"
    assert "+python-dotenv" in result["diff"]
    assert result["run_dir"].startswith(str(runs))
    json.dumps(result)  # must be plain JSON for the protocol
    settings = fake_check[0][2]
    assert settings.sandbox == "local" and settings.out_dir == runs.resolve()
    assert [e[0] for e in events] == ["stage", "warn"]


def test_check_rejects_bad_arguments(fake_check):
    assert "error" in mcp_server.run_and_summarize("x", sandbox="vm")
    assert "error" in mcp_server.run_and_summarize("x", max_rounds=9)
    assert fake_check == []


def test_max_rounds_zero_means_no_repair(fake_check):
    mcp_server.run_and_summarize("examples/quote-of-the-day", max_rounds=0)
    assert fake_check[0][2].repair is False


def test_pass_env_only_forwards_named_variables(fake_check, monkeypatch):
    monkeypatch.setenv("DEMO_API_KEY", "abc")
    monkeypatch.setenv("UNRELATED_SECRET", "nope")
    mcp_server.run_and_summarize("examples/x", pass_env=["DEMO_API_KEY", "MISSING_ONE"])
    assert fake_check[0][2].env == {"DEMO_API_KEY": "abc"}


def test_long_diff_is_truncated(runs):
    report = fake_report()
    report.final_diff = "+x\n" * 20_000
    result = mcp_server.summarize(report, runs)
    assert len(result["diff"]) < 21_000 and "truncated" in result["diff"]


def test_report_reads_only_inside_runs_folder(runs, tmp_path):
    run = runs / "20261024-000000-demo"
    run.mkdir(parents=True)
    (run / "report.md").write_text("# report\n")
    assert mcp_server.read_report(run.name) == "# report\n"
    assert mcp_server.read_report(str(run)) == "# report\n"
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "report.md").write_text("secret")
    for bad in (str(tmp_path / "elsewhere"), "../elsewhere"):
        with pytest.raises(ValueError):
            mcp_server.read_report(bad)


def test_protocol_lists_tools_and_calls_one(fake_check):
    async def main():
        async with Client(mcp_server.build_server()) as client:
            tools = await client.list_tools()
            names = sorted(t.name for t in tools.tools)
            result = await client.call_tool("firstrun_check", {
                "target": "examples/quote-of-the-day", "sandbox": "local", "offline": True,
            })
            return names, result

    names, result = asyncio.run(main())
    assert names == ["firstrun_check", "firstrun_plan", "firstrun_report"]
    assert not result.is_error
    data = result.structured_content or json.loads(result.content[0].text)
    if "result" in data and isinstance(data["result"], dict):
        data = data["result"]
    assert data["verdict"] == "fixed"


def test_stdio_subprocess_handshake():
    """The real `python -m firstrun.mcp_server` speaks MCP on stdout and nothing else."""
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "firstrun.mcp_server"], cwd=str(ROOT),
        env={**os.environ, "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""},
    )

    async def main():
        async with Client(params, read_timeout_seconds=30) as client:
            tools = await client.list_tools()
            plan = await client.call_tool("firstrun_plan", {"target": str(EXAMPLES / "standup-notes")})
            return tools, plan

    tools, plan = asyncio.run(main())
    assert {t.name for t in tools.tools} == {"firstrun_check", "firstrun_plan", "firstrun_report"}
    data = plan.structured_content or json.loads(plan.content[0].text)
    if "result" in data and isinstance(data["result"], dict):
        data = data["result"]
    assert "python summarize.py notes.txt" in [s["command"] for s in data["steps"]]

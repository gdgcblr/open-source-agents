import pytest

from firstrun.comment import MARKER, MAX_COMMENT_CHARS, render_badge, render_comment
from firstrun.models import (
    Diagnosis, Edit, Evidence, Plan, Report, Round, RunResult, Skipped, Step, StepResult,
)

DIFF = (
    "diff --git a/requirements.txt b/requirements.txt\n"
    "--- a/requirements.txt\n+++ b/requirements.txt\n"
    "@@ -1 +1,2 @@\n colorama==0.4.6\n+python-dotenv\n"
)


def steps():
    return [Step(1, "pip install -r requirements.txt", line=18), Step(2, "python main.py --day 3", kind="run", line=24)]


def run(label, status, failing_output=None):
    s1, s2 = steps()
    if failing_output is None:
        results = [StepResult(s1, "passed", 0, "ok", 2.0), StepResult(s2, "passed", 0, "Quote #3", 0.2)]
    else:
        results = [StepResult(s1, "passed", 0, "ok", 2.0), StepResult(s2, "failed", 1, failing_output, 0.2)]
    return RunResult(label, status, results, 2.2, "docker python:3.12-slim", "raw log")


def report(verdict, **kw):
    base = dict(
        project="quote-of-the-day",
        source="/home/runner/work/open-source-agents/open-source-agents/agents/quote-of-the-day",
        started_at="2026-10-24T12:00:00+05:30", finished_at="2026-10-24T12:01:00+05:30",
        verdict=verdict, headline=f"headline for {verdict}",
        documented_plan=Plan(steps=steps(), skipped=[Skipped(".venv\\Scripts\\activate", "windows-only", 14)]),
        documented_run=None,
        settings={"sandbox": "docker", "sandbox_detail": "docker python:3.12-slim",
                  "engine": "rules (offline)", "duration_seconds": 41.2, "env_keys": ["GEMINI_API_KEY"]},
    )
    base.update(kw)
    return Report(**base)


TRACEBACK = "Traceback (most recent call last):\n" + "\n".join(f"  frame {i}" for i in range(20)) + \
    "\nModuleNotFoundError: No module named 'dotenv'"

DIAG = Diagnosis(
    category="missing_dependency",
    summary="main.py imports dotenv, but requirements.txt does not declare python-dotenv.",
    evidence=[Evidence("main.py", 3, "imports dotenv"), Evidence("requirements.txt", None, "only lists colorama")],
    edits=[Edit("requirements.txt", "", "python-dotenv\n")],
    confidence="high",
)


def fixed_report():
    return report(
        "fixed",
        documented_run=run("as documented", "failed", TRACEBACK),
        rounds=[Round(1, DIAG, diff=DIFF, verification=run("after fix 1", "passed"))],
        final_diff=DIFF,
    )


def test_fixed_comment_has_the_whole_story():
    body = render_comment(fixed_report())
    assert body.splitlines()[0] == MARKER
    assert "**FirstRun: FIXED** for `quote-of-the-day`" in body
    assert "headline for fixed" in body
    assert "step 2 `python main.py --day 3` (README line 24) failed with exit 1" in body
    assert "ModuleNotFoundError: No module named 'dotenv'" in body
    assert "frame 5" not in body  # only the last few lines of output
    assert "- `main.py:3` imports dotenv" in body
    assert "```diff\n" + DIFF.rstrip() + "\n```" in body
    assert "Verified: with this patch" in body
    assert "git apply --directory=agents/quote-of-the-day fix.patch" in body
    assert "<details><summary>Steps FirstRun ran</summary>" in body
    assert "**after fix 1**" in body
    assert "windows-only" in body


def test_passed_comment_is_short():
    body = render_comment(report("passed", documented_run=run("as documented", "passed")))
    assert body.startswith(MARKER)
    assert "**FirstRun: PASSED**" in body
    assert "all 2 steps passed" in body
    assert "```diff" not in body and "Why:" not in body


def test_blocked_comment_names_the_key_and_does_not_fake_anything():
    diag = Diagnosis(category="credentials_required", summary="haiku.py needs GEMINI_API_KEY.",
                     blocked=True, missing_env=["GEMINI_API_KEY"])
    body = render_comment(report("blocked", documented_run=run("as documented", "failed", "error: missing API key"),
                                 rounds=[Round(1, diag)]))
    assert "**FirstRun: BLOCKED**" in body
    assert "Needs `GEMINI_API_KEY`" in body and "Nothing was faked" in body
    assert "```diff" not in body


def test_failed_comment_marks_patch_as_not_verified():
    still_broken = run("after fix 1", "failed", "ImportError: cannot import name 'x'")
    body = render_comment(report(
        "failed", documented_run=run("as documented", "failed", TRACEBACK),
        rounds=[Round(1, DIAG, diff=DIFF, verification=still_broken)], final_diff=DIFF,
    ))
    assert "**FirstRun: FAILED**" in body
    assert "Not verified: with this patch the setup still stops at step 2" in body


def test_error_comment_without_runs():
    body = render_comment(report("error", documented_plan=None, error="Docker is not running",
                                 headline="FirstRun could not finish: Docker is not running"))
    assert "**FirstRun: ERROR**" in body
    assert "Docker is not running" in body
    assert "As documented" not in body and "<details>" not in body


def test_multiple_rounds_are_labelled():
    second = Diagnosis(category="undocumented_step", summary="README never copies .env.example.")
    r = fixed_report()
    r.rounds.append(Round(2, second, diff=DIFF, verification=run("after fix 2", "passed")))
    body = render_comment(r)
    assert "**Why (round 1):**" in body and "**Why (round 2):**" in body


def test_long_diff_is_truncated_and_comment_stays_under_limit():
    huge = "diff --git a/README.md b/README.md\n" + "".join(f"+line {i} {'x' * 80}\n" for i in range(5000))
    r = fixed_report()
    r.final_diff = huge
    body = render_comment(r)
    assert len(body) < MAX_COMMENT_CHARS
    assert "diff truncated" in body and "more lines in fix.patch" in body


def test_giant_output_still_fits():
    many = [StepResult(Step(i, f"echo {i} " + "y" * 200), "passed", 0, "", 0.1) for i in range(1, 1200)]
    r = fixed_report()
    r.documented_run = RunResult("as documented", "failed", many + r.documented_run.results[1:], 9.0, "docker", "")
    body = render_comment(r)
    assert len(body) <= MAX_COMMENT_CHARS
    assert body.startswith(MARKER)
    # the step tables are the first thing dropped, the story stays
    assert "<details>" not in body and "```diff" in body


def test_no_secret_values_leak():
    r = fixed_report()
    # even if a caller stuffed values into settings by mistake, the comment never prints settings env
    r.settings["env"] = {"GEMINI_API_KEY": "AIzaSy-real-looking-secret"}
    body = render_comment(r)
    assert "AIzaSy-real-looking-secret" not in body
    assert "env_keys" not in body


def test_unknown_project_path_falls_back_to_generic_apply_hint():
    r = fixed_report()
    r.source = "https://github.com/someone/single-project"
    body = render_comment(r)
    assert "`git apply fix.patch`" in body and "--directory=<project folder>" in body
    assert "--directory=tools/x" in render_comment(r, project_path="tools/x/")
    # a sample nested under our own folder is not agents/readme-first-run
    r.source = "/Users/me/open-source-agents/agents/readme-first-run/examples/quote-of-the-day"
    assert "--directory=<project folder>" in render_comment(r)
    r.source = "https://github.com/gdgcblr/open-source-agents (agents/cool-agent)"
    assert "--directory=agents/cool-agent" in render_comment(r)
    r.source = "https://github.com/a/b/tree/feat/x/tools/mcp-thing"
    assert "--directory=tools/mcp-thing" in render_comment(r)


def test_backticks_in_commands_do_not_break_markdown():
    r = fixed_report()
    r.documented_run.results[1].step.command = "echo `date` && python main.py"
    body = render_comment(r)
    assert "`echo 'date' && python main.py`" in body


@pytest.mark.parametrize("verdict,message,color", [
    ("passed", "works%20as%20documented", "brightgreen"),
    ("fixed", "fix%20available", "yellow"),
    ("blocked", "needs%20credentials", "lightgrey"),
    ("failed", "broken", "red"),
    ("error", "not%20checked", "lightgrey"),
])
def test_badges(verdict, message, color):
    badge = render_badge(report(verdict))
    assert badge.startswith("![FirstRun: ")
    assert f"https://img.shields.io/badge/FirstRun-{message}-{color})" in badge


def test_badge_link_and_escaping():
    linked = render_badge(report("passed"), link="https://example.com/report.md")
    assert linked.startswith("[![FirstRun") and linked.endswith("](https://example.com/report.md)")
    from firstrun.comment import _shield
    assert _shield("a-b_c d") == "a--b__c%20d"

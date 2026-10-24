import json
from pathlib import Path

import pytest

from firstrun.ai import ai_extract_plan, ai_investigate, ai_output_check, run_tool
from firstrun.llm import FakeLLM, LLMError
from firstrun.models import Diagnosis, Edit, Plan, Round, RunResult, Skipped, Step, StepResult
from firstrun.repair import apply_edits, copy_project

README = """# Quote CLI

Prints a quote of the day.

## Prerequisites

- Python 3.10+
- uv (optional, for faster installs)

## Installation

```bash
git clone https://github.com/someone/quote-cli.git
cd quote-cli
pip install -r requirements.txt
```

## How to Run

```bash
python main.py
```
"""
# 1-based README lines of the commands above
LINE_PIP = 15
LINE_RUN = 21

MAIN = """import os

from dotenv import load_dotenv
import colorama

load_dotenv()
print("Stay hungry, stay foolish.")
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "quote-cli"
    root.mkdir()
    (root / "README.md").write_text(README)
    (root / "requirements.txt").write_text("colorama\n")
    (root / "main.py").write_text(MAIN)
    return root


@pytest.fixture
def draft():
    return Plan(
        steps=[
            Step(index=1, command="pip install -r requirements.txt", kind="setup", section="Installation", line=LINE_PIP),
            Step(index=2, command="python main.py", kind="run", section="How to Run", line=LINE_RUN),
        ],
        skipped=[
            Skipped(command="git clone https://github.com/someone/quote-cli.git", reason="git clone", line=13),
            Skipped(command="cd quote-cli", reason="cd into the project", line=14),
        ],
        readme_path="README.md",
        engine="rules",
    )


def failed_run():
    steps = [
        Step(index=1, command="pip install -r requirements.txt", line=LINE_PIP),
        Step(index=2, command="python main.py", kind="run", line=LINE_RUN),
    ]
    out = ('Traceback (most recent call last):\n  File "/work/main.py", line 3, in <module>\n'
           "    from dotenv import load_dotenv\nModuleNotFoundError: No module named 'dotenv'\n")
    return RunResult(
        label="as documented",
        status="failed",
        results=[
            StepResult(step=steps[0], status="passed", exit_code=0, output="Successfully installed colorama", duration=2.0),
            StepResult(step=steps[1], status="failed", exit_code=1, output=out, duration=0.1),
        ],
        duration=2.1,
        sandbox="docker python:3.12-slim",
        log="",
    )


def plan_reply(**overrides):
    reply = {
        "steps": [
            {"command": "pip install -r requirements.txt", "kind": "setup", "section": "Installation", "line": LINE_PIP},
            {"command": "python main.py", "kind": "run", "section": "How to Run", "line": LINE_RUN},
        ],
        "skipped": [{"command": "git clone https://github.com/someone/quote-cli.git", "reason": "git clone"}],
        "required_env": ["QUOTE_CATEGORY", "not a var"],
        "expected_output": None,
        "notes": ["install path is clear"],
    }
    reply.update(overrides)
    return reply


DOTENV_FINAL = {"final": {
    "category": "missing_dependency",
    "summary": "main.py imports dotenv but requirements.txt does not list python-dotenv, so `python main.py` fails on a fresh install.",
    "explanation": "pip installed only colorama.",
    "evidence": [{"file": "main.py", "line": 3, "note": "from dotenv import load_dotenv"},
                 {"file": "requirements.txt", "line": 1, "note": "only colorama"}],
    "edits": [{"path": "requirements.txt", "old": "", "new": "python-dotenv\n"}],
    "blocked": False,
    "missing_env": [],
    "confidence": "high",
}}


def user_texts(fake, call_index):
    return [m["text"] for m in fake.calls[call_index]["messages"] if m["role"] == "user"]


# ---------------------------------------------------------------- planning


def test_plan_happy_path(project, draft):
    fake = FakeLLM([plan_reply()])
    plan = ai_extract_plan(fake, project, draft)
    assert plan.engine == "gemini"
    assert [s.command for s in plan.steps] == ["pip install -r requirements.txt", "python main.py"]
    assert [s.index for s in plan.steps] == [1, 2]
    assert plan.steps[1].kind == "run"
    assert plan.required_env == ["QUOTE_CATEGORY"]
    assert plan.skipped[0].reason == "git clone"
    assert "install path is clear" in plan.notes
    first = fake.calls[0]["messages"][0]["text"]
    assert f"{LINE_RUN} | python main.py" in first
    assert "Draft plan from the rule-based extractor" in first


def test_plan_reanchors_wrong_line_numbers(project, draft):
    pytest.importorskip("firstrun.readme")
    reply = plan_reply()
    reply["steps"][1]["line"] = 3
    plan = ai_extract_plan(FakeLLM([reply]), project, draft)
    assert plan.steps[1].line == LINE_RUN


def test_plan_invalid_json_falls_back_to_draft(project, draft):
    plan = ai_extract_plan(FakeLLM(["I could not read that README, sorry"]), project, draft)
    assert plan.engine == "rules"
    assert [s.command for s in plan.steps] == [s.command for s in draft.steps]
    assert any("AI planning failed" in n for n in plan.notes)


def test_plan_llm_error_falls_back(project, draft):
    plan = ai_extract_plan(FakeLLM([LLMError("quota")]), project, draft)
    assert plan.engine == "rules"
    assert any("quota" in n for n in plan.notes)


def test_plan_rewritten_command_is_sent_back_and_corrected(project, draft):
    rewritten = plan_reply()
    rewritten["steps"][0]["command"] = "pip install -q -r requirements.txt python-dotenv"
    fake = FakeLLM([rewritten, plan_reply()])
    plan = ai_extract_plan(fake, project, draft)
    assert len(fake.calls) == 2
    retry = user_texts(fake, 1)[-1]
    assert "does not appear verbatim" in retry
    assert plan.steps[0].command == "pip install -r requirements.txt"
    assert plan.engine == "gemini"


def test_plan_still_rewritten_after_retry_is_dropped(project, draft):
    rewritten = plan_reply()
    rewritten["steps"][1]["command"] = "python3 main.py --fixed"
    plan = ai_extract_plan(FakeLLM([rewritten, rewritten]), project, draft)
    assert [s.command for s in plan.steps] == ["pip install -r requirements.txt"]
    assert any("dropped steps" in n for n in plan.notes)


def test_plan_with_nothing_usable_keeps_draft(project, draft):
    bad = plan_reply(steps=[{"command": "make everything work"}])
    plan = ai_extract_plan(FakeLLM([bad, bad]), project, draft)
    assert plan.engine == "rules"
    assert [s.command for s in plan.steps] == [s.command for s in draft.steps]


def test_plan_prerequisite_only_for_named_tools(project, draft):
    reply = plan_reply()
    reply["steps"].insert(0, {"command": "pip install uv", "provided_by_firstrun": True, "kind": "prerequisite"})
    plan = ai_extract_plan(FakeLLM([reply]), project, draft)
    assert plan.steps[0].command == "pip install uv"
    assert plan.steps[0].provided_by_firstrun and plan.steps[0].kind == "prerequisite"

    sneaky = plan_reply()
    sneaky["steps"].insert(0, {"command": "pip install python-dotenv", "provided_by_firstrun": True})
    fake = FakeLLM([sneaky, sneaky])
    plan = ai_extract_plan(fake, project, draft)
    assert "pip install python-dotenv" not in [s.command for s in plan.steps]
    assert "provided_by_firstrun" in user_texts(fake, 1)[-1]


def test_plan_without_readme(tmp_path, draft):
    plan = ai_extract_plan(FakeLLM([]), tmp_path, draft)
    assert plan.engine == "rules"
    assert any("no README" in n for n in plan.notes)


# ---------------------------------------------------------------- investigating


def test_investigator_reads_a_file_then_fixes(project, draft, tmp_path):
    events = []
    fake = FakeLLM([{"tool": "read_file", "args": {"path": "main.py"}}, DOTENV_FINAL])
    d = ai_investigate(fake, project, draft, failed_run(), on_event=lambda k, m, data=None: events.append((k, data)))

    assert d.engine == "gemini"
    assert d.category == "missing_dependency"
    assert d.confidence == "high"
    assert d.evidence[0].file == "main.py" and d.evidence[0].line == 3
    assert d.trace == [{"tool": "read_file", "args": {"path": "main.py"},
                        "result_preview": d.trace[0]["result_preview"]}]
    assert "from dotenv import load_dotenv" in d.trace[0]["result_preview"]
    assert events == [("tool_call", {"tool": "read_file", "args": {"path": "main.py"}})]

    context = user_texts(fake, 0)[0]
    assert "ModuleNotFoundError: No module named 'dotenv'" in context
    assert "[failed, exit 1] step 2: python main.py" in context
    assert "main.py lines 1-" in user_texts(fake, 1)[-1]

    patched = copy_project(project, tmp_path / "patched")
    apply_edits(patched, d.edits)
    assert (patched / "requirements.txt").read_text() == "colorama\npython-dotenv\n"


def test_investigator_search_tool(project):
    out = run_tool(project, "search", {"pattern": "load_dotenv"})
    assert "main.py:3: from dotenv import load_dotenv" in out
    assert "main.py:6: load_dotenv()" in out
    # a broken regex is searched as literal text instead of erroring
    assert run_tool(project, "search", {"pattern": "load_dotenv("}) == "main.py:6: load_dotenv()"
    assert "requirements.txt" in run_tool(project, "list_files", {"path": ""})
    assert "unknown tool" in run_tool(project, "rm", {})


def test_invalid_edit_gets_one_corrected_retry(project, draft):
    bad = json.loads(json.dumps(DOTENV_FINAL))
    bad["final"]["edits"] = [{"path": "requirements.txt", "old": "numpy\n", "new": "numpy\npython-dotenv\n"}]
    fake = FakeLLM([bad, DOTENV_FINAL])
    d = ai_investigate(fake, project, draft, failed_run())
    assert len(fake.calls) == 2
    assert "cannot be applied" in user_texts(fake, 1)[-1]
    assert d.edits == [Edit(path="requirements.txt", old="", new="python-dotenv\n")]


def test_invalid_edit_twice_uses_rule_hint(project, draft):
    bad = json.loads(json.dumps(DOTENV_FINAL))
    bad["final"]["edits"] = [{"path": "requirements.txt", "old": "numpy\n", "new": "x"}]
    hint = Diagnosis(category="missing_dependency", summary="rule says add python-dotenv",
                     edits=[Edit(path="requirements.txt", old="", new="python-dotenv\n")], engine="rules")
    d = ai_investigate(FakeLLM([bad, bad]), project, draft, failed_run(), hint=hint)
    assert d.engine == "rules"
    assert d.summary == "rule says add python-dotenv"
    assert "fell back to the rule-based diagnosis" in d.explanation


def test_invalid_edit_twice_without_hint_drops_edits(project, draft):
    bad = json.loads(json.dumps(DOTENV_FINAL))
    bad["final"]["edits"] = [{"path": "requirements.txt", "old": "numpy\n", "new": "x"}]
    d = ai_investigate(FakeLLM([bad, bad]), project, draft, failed_run())
    assert d.edits == []
    assert d.confidence == "low"
    assert d.category == "missing_dependency"


def test_tool_budget_forces_a_final(project, draft):
    calls = [{"tool": "list_files", "args": {}}] * 3
    fake = FakeLLM(calls + [DOTENV_FINAL])
    d = ai_investigate(fake, project, draft, failed_run(), max_tool_calls=2)
    assert len(d.trace) == 2
    assert d.category == "missing_dependency"
    assert any("Tool budget used up" in t for t in user_texts(fake, 3))


def test_model_that_never_finishes_falls_back(project, draft):
    fake = FakeLLM([{"tool": "list_files", "args": {}}] * 20)
    d = ai_investigate(fake, project, draft, failed_run(), max_tool_calls=2)
    assert d.category == "unknown"
    assert len(d.trace) == 2


def test_path_escape_is_refused(project, draft, tmp_path):
    (tmp_path / "secret.txt").write_text("hunter2")
    for path in ("../secret.txt", str(tmp_path / "secret.txt"), "/etc/passwd"):
        out = run_tool(project, "read_file", {"path": path})
        assert out.startswith("error:") and "hunter2" not in out
    assert run_tool(project, "list_files", {"path": "../"}).startswith("error:")

    fake = FakeLLM([{"tool": "read_file", "args": {"path": "../secret.txt"}}, DOTENV_FINAL])
    d = ai_investigate(fake, project, draft, failed_run())
    assert "escapes" in d.trace[0]["result_preview"]
    assert "hunter2" not in json.dumps(fake.calls)


def test_escaping_edit_is_rejected(project, draft):
    bad = json.loads(json.dumps(DOTENV_FINAL))
    bad["final"]["edits"] = [{"path": "../evil.txt", "old": "", "new": "x"}]
    d = ai_investigate(FakeLLM([bad, bad]), project, draft, failed_run())
    assert d.edits == []


def test_credentials_are_blocked_and_never_invented(project, draft):
    run = failed_run()
    run.results[1].output = "KeyError: 'GEMINI_API_KEY'\n"
    creds = {"final": {
        "category": "credentials_required",
        "summary": "The haiku step needs GEMINI_API_KEY, which a newcomer has to supply.",
        "evidence": [{"file": "main.py", "line": 5, "note": "reads GEMINI_API_KEY"}],
        "edits": [],
        "blocked": False,
        "missing_env": ["GEMINI_API_KEY", "lowercase_is_not_a_var"],
    }}
    d = ai_investigate(FakeLLM([creds]), project, draft, run)
    assert d.blocked is True
    assert d.missing_env == ["GEMINI_API_KEY"]
    assert d.edits == []


def test_secret_looking_edit_is_rejected(project, draft):
    leak = {"final": {
        "category": "credentials_required",
        "summary": "needs a key",
        "edits": [{"path": ".env.example", "old": "", "new": "GEMINI_API_KEY=AIzaSyA1234567890abcdefghijklmnopqrs\n"}],
    }}
    fake = FakeLLM([leak, leak])
    d = ai_investigate(fake, project, draft, failed_run())
    assert "looks like a real credential" in user_texts(fake, 1)[-1]
    assert d.edits == []
    assert d.blocked


def test_credentials_fix_cannot_touch_code(project, draft):
    sneaky = {"final": {
        "category": "credentials_required",
        "summary": "needs a key",
        "blocked": "false",
        "edits": [{"path": "main.py", "old": "load_dotenv()\n", "new": "os.environ['GEMINI_API_KEY'] = 'demo'\n"}],
    }}
    fake = FakeLLM([sneaky, sneaky])
    d = ai_investigate(fake, project, draft, failed_run())
    assert "only .env.example or the README" in user_texts(fake, 1)[-1]
    assert d.edits == [] and d.blocked


def test_string_booleans_from_the_model(project, draft):
    reply = plan_reply()
    reply["steps"][1]["long_running"] = "false"
    plan = ai_extract_plan(FakeLLM([reply]), project, draft)
    assert plan.steps[1].long_running is False
    final = json.loads(json.dumps(DOTENV_FINAL))
    final["final"]["blocked"] = "false"
    assert ai_investigate(FakeLLM([final]), project, draft, failed_run()).blocked is False


def test_llm_error_falls_back_to_hint_with_trace(project, draft):
    hint = Diagnosis(category="missing_dependency", summary="rule hint", engine="rules")
    fake = FakeLLM([{"tool": "read_file", "args": {"path": "main.py"}}, LLMError("503 overloaded")])
    d = ai_investigate(fake, project, draft, failed_run(), hint=hint)
    assert d.summary == "rule hint"
    assert len(d.trace) == 1
    assert "503 overloaded" in d.explanation


def test_malformed_replies_end_in_unknown(project, draft):
    d = ai_investigate(FakeLLM([{"thoughts": "hmm"}, {"thoughts": "still hmm"}]), project, draft, failed_run())
    assert d.category == "unknown"
    assert d.engine == "gemini"


def test_hint_and_history_reach_the_model(project, draft):
    hint = Diagnosis(category="missing_dependency", summary="rule hint about python-dotenv")
    earlier = Round(
        number=1,
        diagnosis=Diagnosis(category="undocumented_step", summary="tried adding an install step",
                            edits=[Edit(path="README.md", old="", new="x")]),
        verification=failed_run(),
    )
    fake = FakeLLM([DOTENV_FINAL])
    ai_investigate(fake, project, draft, failed_run(), hint=hint, history=[earlier])
    context = user_texts(fake, 0)[0]
    assert "rule hint about python-dotenv" in context
    assert "Round 1: undocumented_step: tried adding an install step (edited README.md)" in context
    assert "Re-run from scratch: failed" in context


# ---------------------------------------------------------------- output check


def test_output_check_without_llm():
    same = ai_output_check(None, "Quote of the day:\n  Stay hungry.\n", "Quote of the day:\n  Stay hungry.")
    assert same["similarity"] == 1.0 and same["verdict"] == "matches"
    diff = ai_output_check(None, "Weather: 24C sunny", "Traceback (most recent call last): boom")
    assert diff["verdict"] == "differs"


def test_output_check_with_llm_and_failure():
    fake = FakeLLM([{"verdict": "matches", "note": "only the quote changed"}])
    res = ai_output_check(fake, "Quote: A", "Quote: B, a totally different random quote")
    assert res["verdict"] == "matches" and res["note"] == "only the quote changed"
    res = ai_output_check(FakeLLM([LLMError("down")]), "a", "a")
    assert res["verdict"] == "matches" and "model check failed" in res["note"]

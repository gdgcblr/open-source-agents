from conftest import GOOD_README, good_files

from judge.analyzers import ai_native, compliance, docs, quality, reproducibility
from judge.models import SubmissionMeta


def check(result, cid):
    return next(c for c in result.checks if c.id == cid)


# ---- compliance -------------------------------------------------------------------------------
def test_compliance_passes_for_template_layout(make_ws):
    r = compliance.analyze(make_ws(good_files()))
    assert {c.id: c.status for c in r.checks} == {
        "location": "pass",
        "kebab_case": "pass",
        "descriptive_name": "pass",
        "required_files": "pass",
        "scope": "pass",
        "no_junk": "pass",
    }


def test_generic_and_non_kebab_names(make_ws):
    assert check(compliance.analyze(make_ws(good_files(), slug="demo")), "descriptive_name").status == "warn"
    assert check(compliance.analyze(make_ws(good_files(), slug="My_Agent")), "kebab_case").status == "fail"


def test_out_of_scope_changes_gate_but_index_row_is_allowed(make_ws):
    ws = make_ws(good_files())
    ws.meta = SubmissionMeta(
        id="3",
        number=3,
        state="open",
        title="feat(agents): add meeting-summarizer",
        body="- [x] a\n- [x] b\n- [x] c\n- [ ] d",
    )
    ws.changed_paths += ["agents/README.md", "README.md"]
    ws.changed_lines = {"agents/README.md": 1, "README.md": 10}
    r = compliance.analyze(ws)
    assert check(r, "scope").status == "fail"
    assert [f.file for f in r.findings if f.gate] == ["README.md"]
    assert check(r, "pr_checklist").status == "pass"
    assert check(r, "pr_title").status == "pass"


def test_extra_new_project_folder_is_in_scope(make_ws):
    ws = make_ws(good_files())
    ws.changed_paths += ["tools/civic-mcp/server.py"]
    ws.extra_projects = ["tools/civic-mcp"]
    assert check(compliance.analyze(ws), "scope").status == "pass"


# ---- reproducibility ----------------------------------------------------------------------------
def test_imports_must_be_declared(make_ws):
    files = good_files(**{"extra.py": "import requests\nimport yaml\nfrom dotenv import load_dotenv\n"})
    r = reproducibility.analyze(make_ws(files))
    c = check(r, "deps_declared")
    assert c.status == "fail" and {"requests", "pyyaml", "python-dotenv"} <= set(r.facts["undeclared"])


def test_transitive_and_optional_imports_are_accepted(make_ws):
    files = good_files(
        **{
            "requirements.txt": "google-adk>=1.0\n",
            "agent.py": "from google.genai import types\nimport pydantic\ntry:\n    import rich\nexcept ImportError:\n"
            "    rich = None\n",
        }
    )
    r = reproducibility.analyze(make_ws(files))
    assert check(r, "deps_declared").status == "pass", r.facts["undeclared"]


def test_env_vars_must_be_documented(make_ws):
    files = good_files(**{"cfg.py": "import os\nTOKEN = os.environ['SLACK_TOKEN']\nM = os.getenv('MODEL_NAME')\n"})
    r = reproducibility.analyze(make_ws(files))
    assert check(r, "env_documented").status == "warn"
    assert "SLACK_TOKEN" in check(r, "env_documented").detail


def test_run_command_must_resolve(make_ws):
    assert check(reproducibility.analyze(make_ws(good_files())), "run_command").status == "pass"
    broken = GOOD_README.replace("python main.py", "python app.py")
    r = reproducibility.analyze(make_ws(good_files(**{"README.md": broken})))
    assert check(r, "run_command").status == "fail"


def test_syntax_errors_fail(make_ws):
    r = reproducibility.analyze(make_ws(good_files(**{"bad.py": "def x(:\n"})))
    assert check(r, "compiles").status == "fail"


# ---- docs ---------------------------------------------------------------------------------------
def test_complete_readme_scores_well(make_ws):
    r = docs.analyze(make_ws(good_files()))
    assert check(r, "sections").status == "pass"
    assert check(r, "placeholders").status == "pass"
    assert check(r, "examples").status == "pass"  # examples live in ### sub-sections


def test_template_placeholders_are_caught(make_ws):
    template = (
        "# [Project Name]\n\n> [One-sentence summary of what this project does]\n\n"
        "## Overview\n- Feature 1: Brief description of the capability.\n"
    )
    r = docs.analyze(make_ws(good_files(**{"README.md": template})))
    assert check(r, "placeholders").status == "warn" or check(r, "placeholders").status == "fail"
    assert r.facts["placeholders"] == 3


# ---- quality ------------------------------------------------------------------------------------
def test_quality_rewards_tests_and_penalises_swallowed_errors(make_ws):
    r = quality.analyze(make_ws(good_files()), run_ruff=False)
    assert check(r, "tests").status == "pass"
    bad = good_files(**{"util.py": "def f():\n    try:\n        return 1\n    except:\n        pass\n"})
    bad.pop("tests/test_main.py")
    r = quality.analyze(make_ws(bad, slug="other-agent"), run_ruff=False)
    assert check(r, "tests").status == "fail"
    assert check(r, "error_handling").status == "warn"


# ---- AI-native ladder ---------------------------------------------------------------------------
def level(make_ws, slug, files, category="agents"):
    return ai_native.analyze(make_ws(files, slug=slug, category=category)).facts["ai_level"]


def test_ladder_levels(make_ws):
    wrapper = (
        "from google import genai\nc = genai.Client()\nprint(c.models.generate_content(model='m', contents='hi'))\n"
    )
    assert level(make_ws, "lvl-one", {"main.py": wrapper}) == 1
    assert level(make_ws, "lvl-two", good_files()) == 2  # structured output + system instruction
    tools = wrapper + "c.models.generate_content(model='m', contents='x', config={'tools': [lookup]})\n"
    assert level(make_ws, "lvl-three", {"main.py": tools}) == 3
    agent = "from google.adk.agents import Agent\nroot_agent = Agent(name='a', model='m', tools=[lookup])\n"
    assert level(make_ws, "lvl-four", {"agent.py": agent}) == 4
    multi = agent + "boss = Agent(name='b', model='m', sub_agents=[root_agent], tools=[t])\n"
    assert level(make_ws, "lvl-five", {"agent.py": multi}) == 5


def test_mcp_server_without_model_calls_is_tool_use_not_agent(make_ws):
    server = (
        "from mcp.server.fastmcp import FastMCP\nmcp = FastMCP('x')\n\n@mcp.tool()\ndef add(a: int) -> int:\n"
        "    return a\n\nmcp.run(transport='stdio')\n"
    )
    r = ai_native.analyze(make_ws({"server.py": server}, slug="adder-mcp", category="tools"))
    assert r.facts["ai_level"] == 3 and r.facts["llm_sites"] == []


def test_go_adk_agent_is_detected(make_ws):
    go = (
        'package main\nimport (\n\t"google.golang.org/adk/v2/agent/llmagent"\n\t"google.golang.org/genai"\n)\n'
        "func main() {\n\ta, err := llmagent.New(llmagent.Config{Tools: tools})\n\tif err != nil {}\n}\n"
    )
    r = ai_native.analyze(make_ws({"main.go": go}, slug="triage-go"))
    assert "Google ADK" in r.facts["frameworks"] and "Gemini" in r.facts["providers"]
    assert r.facts["ai_level"] == 4

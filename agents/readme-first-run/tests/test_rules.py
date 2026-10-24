import shutil
from pathlib import Path

import pytest

from firstrun import rules
from firstrun.models import RunResult, StepResult
from firstrun.readme import extract_plan
from firstrun.repair import apply_edits, validate_edits

TEMPLATE = Path(__file__).resolve().parents[3] / "template"

VENV_STEPS = "python -m venv .venv\nsource .venv/bin/activate\n"


def project(tmp_path: Path, readme: str, files: dict[str, str]) -> Path:
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def fail_at(plan, command_prefix: str, output: str, exit_code: int = 1, status: str = "failed") -> RunResult:
    """Pretend every step passed until the one starting with command_prefix."""
    results = []
    for step in plan.steps:
        if step.command.startswith(command_prefix):
            results.append(StepResult(step, status, exit_code, output, 0.3))
            break
        results.append(StepResult(step, "passed", 0, "", 0.1))
    else:
        raise AssertionError(f"no step starts with {command_prefix!r}")
    done = len(results)
    results += [StepResult(s, "not_run", None, "", 0.0) for s in plan.steps[done:]]
    return RunResult("as documented", "failed", results, 1.0, "local", output)


def check_edits(proj: Path, diagnosis) -> None:
    assert validate_edits(proj, diagnosis.edits) == []
    apply_edits(proj, diagnosis.edits)


def traceback(module: str, file: str = "main.py") -> str:
    return (
        "Traceback (most recent call last):\n"
        f'  File "/work/{file}", line 3, in <module>\n'
        f"    from {module} import x\n"
        f"ModuleNotFoundError: No module named '{module}'\n"
    )


README_PY = f"""# Quote

## Install

```bash
{VENV_STEPS}pip install -r requirements.txt
```

## Run

```bash
python main.py
```
"""


def test_missing_dotenv_added_to_requirements(tmp_path):
    proj = project(tmp_path, README_PY, {
        "requirements.txt": "colorama==0.4.6\n",
        "main.py": "import os\nfrom colorama import Fore\nfrom dotenv import load_dotenv\n",
    })
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("dotenv")))
    assert d.category == "missing_dependency" and d.confidence == "high"
    assert "python-dotenv" in d.summary and "main.py" in d.summary
    assert any(e.file == "main.py" and e.line == 3 for e in d.evidence)
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text() == "colorama==0.4.6\npython-dotenv\n"


def test_requirements_without_trailing_newline(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "rich", "main.py": "import yaml\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("yaml")))
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text() == "rich\nPyYAML\n"


def test_google_namespace_mapping(tmp_path):
    proj = project(tmp_path, README_PY, {
        "requirements.txt": "requests\n",
        "agent.py": "from google import genai\nfrom google.cloud import storage\n",
        "main.py": "import agent\n",
    })
    assert rules.module_to_package("google", proj) == "google-genai"
    assert rules.module_to_package("google.generativeai") == "google-generativeai"
    assert rules.module_to_package("google.adk.agents") == "google-adk"
    assert rules.module_to_package("google.cloud.bigquery") == "google-cloud-bigquery"
    assert rules.module_to_package("langchain_google_genai") == "langchain-google-genai"
    assert rules.module_to_package("cv2") == "opencv-python"
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("google", "agent.py")))
    assert d.category == "missing_dependency" and "google-genai" in d.summary
    check_edits(proj, d)
    assert "google-genai" in (proj / "requirements.txt").read_text()


def test_wrongly_named_package(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "dotenv\nrich\n", "main.py": "import dotenv\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("dotenv")))
    assert d.category == "missing_dependency" and "python-dotenv" in d.summary
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text() == "python-dotenv\nrich\n"


def test_declared_but_never_installed(tmp_path):
    readme = f"""# Tool

```bash
{VENV_STEPS}```

Then run it:

```bash
python main.py
```
"""
    proj = project(tmp_path, readme, {"requirements.txt": "python-dotenv\n", "main.py": "import dotenv\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("dotenv")))
    assert d.category == "undocumented_step"
    check_edits(proj, d)
    text = (proj / "README.md").read_text()
    assert "pip install -r requirements.txt\npython main.py" in text


def test_local_module_is_not_a_dependency(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "", "src/helpers.py": "", "src/main.py": "import helpers\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("helpers")))
    assert d.category == "wrong_command" and d.edits == [] and d.confidence == "low"


def test_no_manifest_creates_requirements(tmp_path):
    readme = "```bash\npython main.py\n```\n"
    proj = project(tmp_path, readme, {"main.py": "import bs4\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", traceback("bs4")))
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text() == "beautifulsoup4\n"


@pytest.mark.parametrize("output, expected", [
    ("Traceback...\nKeyError: 'GEMINI_API_KEY'\n", ["GEMINI_API_KEY"]),
    ("error: missing API key. Set GEMINI_API_KEY in .env or your shell\n", ["GEMINI_API_KEY"]),
    ("google.genai.errors.ClientError: 400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key.\n", ["GEMINI_API_KEY"]),
    ("openai.AuthenticationError: Error code: 401 - Incorrect API key provided\n", ["GEMINI_API_KEY"]),
    ("ValueError: GEMINI_API_KEY is not set\n", ["GEMINI_API_KEY"]),
    ("google.auth.exceptions.DefaultCredentialsError: Your default credentials were not found.\n", ["GEMINI_API_KEY"]),
])
def test_credentials_are_blocked(tmp_path, output, expected):
    readme = README_PY + "\nSet `GEMINI_API_KEY` in `.env`.\n"
    proj = project(tmp_path, readme, {
        "requirements.txt": "",
        ".env.example": "GEMINI_API_KEY=your_key_here\n",
        "main.py": "import os\nkey = os.environ['GEMINI_API_KEY']\n",
    })
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", output))
    assert d.category == "credentials_required" and d.blocked
    assert d.missing_env[: len(expected)] == expected
    assert d.edits == []  # documented already, nothing to fix
    assert "will not invent" in d.summary


def test_undocumented_credential_goes_into_env_example(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "", "main.py": "import os\nos.getenv('WEATHER_TOKEN')\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", "KeyError: 'WEATHER_TOKEN'\n"))
    assert d.blocked and d.missing_env == ["WEATHER_TOKEN"]
    check_edits(proj, d)
    assert (proj / ".env.example").read_text() == "WEATHER_TOKEN=your_value_here\n"


def test_not_credentials():
    assert rules.detect_credentials("ModuleNotFoundError: No module named 'x'", Path(".")) is None
    assert rules.detect_credentials("Tokenizer loaded 300 tokens\n", Path(".")) is None


@pytest.fixture
def template_project(tmp_path):
    if not (TEMPLATE / "README.md").is_file():
        pytest.skip("repository template not available")
    shutil.copy(TEMPLATE / "README.md", tmp_path / "README.md")
    (tmp_path / "requirements.txt").write_text("")
    (tmp_path / "main.py").write_text("print('hi')\n")
    return tmp_path


def test_npm_leftover_removed_from_template(template_project):
    plan = extract_plan(template_project)
    out = "/firstrun/step_4.sh: line 1: npm: command not found\n"
    d = rules.diagnose(template_project, plan, fail_at(plan, "npm install", out, exit_code=127))
    assert d.category == "template_leftover"
    check_edits(template_project, d)
    text = (template_project / "README.md").read_text()
    assert "npm install" not in text and "npm start" not in text
    assert "For Node.js / TypeScript" not in text and "# Example for Node.js" not in text
    assert "pip install -r requirements.txt" in text and "python main.py" in text
    after = extract_plan(template_project)
    assert not any(s.command.startswith("npm") for s in after.steps)


def test_cli_from_missing_package(tmp_path):
    readme = README_PY.replace("python main.py", "streamlit run app.py")
    proj = project(tmp_path, readme, {"requirements.txt": "pandas\n", "app.py": "import streamlit as st\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "streamlit", "bash: line 1: streamlit: command not found\n", 127))
    assert d.category == "missing_dependency" and "streamlit" in d.summary
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text().endswith("streamlit\n")


def test_package_manager_not_documented(tmp_path):
    proj = project(tmp_path, "```bash\nuv sync\n```\n", {"pyproject.toml": "[project]\nname='x'\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "uv sync", "bash: uv: command not found\n", 127))
    assert d.category == "undocumented_step"
    check_edits(proj, d)
    assert "pip install uv\nuv sync" in (proj / "README.md").read_text()


def test_wrong_script_path(tmp_path):
    readme = README_PY.replace("python main.py", "python summarize.py notes.txt") + (
        "\n## Example\n\n```bash\npython summarize.py notes.txt\n```\n"
    )
    proj = project(tmp_path, readme, {
        "requirements.txt": "",
        "notes.txt": "done: x\n",
        "src/summarize.py": "if __name__ == '__main__':\n    pass\n",
    })
    plan = extract_plan(proj)
    out = "python: can't open file '/work/summarize.py': [Errno 2] No such file or directory\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "python summarize.py", out, 2))
    assert d.category == "wrong_command" and "src/summarize.py" in d.summary
    check_edits(proj, d)
    text = (proj / "README.md").read_text()
    assert text.count("python src/summarize.py notes.txt") == 2
    assert "python summarize.py" not in text


def test_entry_point_by_main_guard(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "", "cli.py": "if __name__ == \"__main__\":\n    print(1)\n"})
    plan = extract_plan(proj)
    out = "python: can't open file '/tmp/x/work/main.py': [Errno 2] No such file or directory\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", out, 2))
    check_edits(proj, d)
    assert "python cli.py" in (proj / "README.md").read_text()


def test_missing_requirements_with_pyproject(tmp_path):
    proj = project(tmp_path, README_PY, {"pyproject.toml": "[project]\nname = 'x'\ndependencies = ['rich']\n", "main.py": ""})
    plan = extract_plan(proj)
    out = "ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "pip install", out))
    assert d.category == "missing_file"
    check_edits(proj, d)
    text = (proj / "README.md").read_text()
    assert "pip install .\n" in text and "requirements.txt" not in text


def test_missing_requirements_generated_from_imports(tmp_path):
    proj = project(tmp_path, README_PY, {"main.py": "import requests\nimport yaml\nimport json\n"})
    plan = extract_plan(proj)
    out = "ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "pip install", out))
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text() == "PyYAML\nrequests\n"


def test_missing_env_file(tmp_path):
    readme = README_PY
    proj = project(tmp_path, readme, {"requirements.txt": "", ".env.example": "MODE=dev\n", "main.py": "open('.env')\n"})
    plan = extract_plan(proj)
    out = "FileNotFoundError: [Errno 2] No such file or directory: '.env'\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", out))
    assert d.category == "undocumented_step"
    check_edits(proj, d)
    assert "cp .env.example .env\npython main.py" in (proj / "README.md").read_text()


def test_data_file_in_another_folder(tmp_path):
    readme = README_PY.replace("python main.py", "python main.py notes.txt")
    proj = project(tmp_path, readme, {"requirements.txt": "", "main.py": "", "data/notes.txt": "x\n"})
    plan = extract_plan(proj)
    out = "FileNotFoundError: [Errno 2] No such file or directory: 'notes.txt'\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", out))
    assert d.category == "wrong_command"
    check_edits(proj, d)
    assert "python main.py data/notes.txt" in (proj / "README.md").read_text()


def test_pinned_version_not_found(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "rich\nnumpy==9.9.9  # fast\n", "main.py": ""})
    plan = extract_plan(proj)
    out = (
        "ERROR: Could not find a version that satisfies the requirement numpy==9.9.9 (from versions: 1.0)\n"
        "ERROR: No matching distribution found for numpy==9.9.9\n"
    )
    d = rules.diagnose(proj, plan, fail_at(plan, "pip install", out))
    assert d.category == "dependency_pin" and d.confidence == "low"
    check_edits(proj, d)
    assert (proj / "requirements.txt").read_text() == "rich\nnumpy\n"


def test_eof_error(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "", "main.py": "input()\n"})
    plan = extract_plan(proj)
    out = 'Traceback...\n  File "main.py", line 1\nEOFError: EOF when reading a line\n'
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", out))
    assert d.category == "interactive_input" and d.edits == [] and not d.blocked


def test_timeout_and_python_version(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "", "main.py": ""})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", "waiting...\n", None, status="timeout"))
    assert d.category == "unknown" and "time limit" in d.summary
    out = "ERROR: Package 'x' requires a different Python: 3.12.4 not in '<3.11'\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "pip install", out))
    assert d.category == "platform_issue"


def test_nothing_matches(tmp_path):
    proj = project(tmp_path, README_PY, {"requirements.txt": "", "main.py": ""})
    plan = extract_plan(proj)
    assert rules.diagnose(proj, plan, fail_at(plan, "python main.py", "ZeroDivisionError: division by zero\n")) is None
    passed = RunResult("as documented", "passed", [StepResult(s, "passed", 0, "", 0.1) for s in plan.steps], 1, "local", "")
    assert rules.diagnose(proj, plan, passed) is None


def test_scan_imports_and_declared(tmp_path):
    proj = project(tmp_path, "# x\n", {
        "requirements.txt": "-r base.txt\nPyYAML>=6 ; python_version >= '3.8'\ngit+https://x/y.git#egg=cool_lib\n-e .\n",
        "base.txt": "python_dotenv[cli]==1.0\n",
        "pyproject.toml": "[project]\nname='x'\ndependencies=['Requests>=2']\n[project.optional-dependencies]\ndev=['pytest']\n",
        "app/__init__.py": "",
        "app/core.py": "import os\nimport yaml\nfrom app import core\nfrom . import x\ntry:\n    import ujson\nexcept ImportError:\n    ujson = None\n",
        "main.py": "import dotenv, requests\nfrom google import genai\n",
    })
    found = rules.scan_imports(proj)
    assert set(found) == {"yaml", "dotenv", "requests", "google"}
    assert found["yaml"] == [("app/core.py", 2)]
    assert rules.declared_packages(proj) == {"pyyaml", "cool-lib", "python-dotenv", "requests", "pytest"}


def test_static_hints(tmp_path):
    proj = project(tmp_path, "# x\nRun it.\n", {
        "requirements.txt": "requests\n",
        "main.py": "import requests\nimport os\nfrom dotenv import load_dotenv\nKEY = os.getenv('GEMINI_API_KEY')\n",
    })
    hints = rules.static_hints(proj)
    assert "main.py:3 imports dotenv, but no manifest declares python-dotenv" in hints
    assert any("GEMINI_API_KEY" in h for h in hints)
    assert not any("requests" in h for h in hints)


def test_static_hints_without_manifest(tmp_path):
    proj = project(tmp_path, "# x\n", {"main.py": "import numpy\n"})
    assert rules.static_hints(proj)[0].startswith("No dependency manifest")


def test_example_projects(tmp_path):
    examples = Path(__file__).resolve().parents[1] / "examples"
    quote = examples / "quote-of-the-day"
    if not quote.is_dir():
        pytest.skip("examples not available")
    hints = rules.static_hints(quote)
    assert any("python-dotenv" in h for h in hints)


# placeholders, missing input files, missing programs, credential ranking (from the event scan)

PDF_README = f"""# PDF QA

## Install

```bash
{VENV_STEPS}pip install -r requirements.txt
```

## How to Run

```bash
python main.py path/to/your/document.pdf
```
"""


def test_placeholder_run_step_is_skipped_and_sample_suggested(tmp_path):
    proj = project(tmp_path, PDF_README, {"requirements.txt": "", "main.py": "print(1)\n",
                                          "examples/paper.pdf": "%PDF-1.4\n"})
    plan = extract_plan(proj)
    assert "python main.py path/to/your/document.pdf" not in [s.command for s in plan.steps]
    skipped = [k for k in plan.skipped if k.command == "python main.py path/to/your/document.pdf"]
    assert skipped[0].reason == "needs your own input (placeholder `path/to/your/document.pdf`)"
    hints = rules.static_hints(proj)
    assert any("examples/paper.pdf is in the project" in h for h in hints)
    assert any("no runnable example" in h for h in hints)


def test_placeholder_without_sample_and_other_examples_still_run(tmp_path):
    readme = PDF_README.replace("document.pdf\n```", "document.pdf\npython main.py report.pdf\n```")
    proj = project(tmp_path, readme, {"requirements.txt": "", "main.py": "print(1)\n"})
    plan = extract_plan(proj)
    assert plan.steps[-1].command == "python main.py report.pdf"
    hints = rules.static_hints(proj)
    assert any("no sample .pdf file in the project" in h for h in hints)
    assert not any("no runnable example" in h for h in hints)


@pytest.mark.parametrize("command", [
    "python -m tool review <PR-or-path> --no-llm",
    "python -m tool review https://github.com/OWNER/REPO",
    "python main.py --file /path/to/error.log --json",
    "python main.py --key YOUR_API_KEY",
    "python3 main.py --pr https://github.com/owner/repository/pull/42",
    "python main.py triage your-org/your-repo",
    "python main.py review owner/repo",
    "python main.py --url https://example.com/page",
])
def test_placeholder_shapes(tmp_path, command):
    readme = f"# t\n\n## Run\n\n```bash\npip install -r requirements.txt\n{command}\npython main.py --url https://docs.python.org/3/\n```\n"
    proj = project(tmp_path, readme, {"requirements.txt": "", "main.py": "print(1)\n"})
    commands = [s.command for s in extract_plan(proj).steps]
    assert command not in commands
    assert "python main.py --url https://docs.python.org/3/" in commands
    assert "pip install -r requirements.txt" in commands


def test_setup_placeholders_keep_their_handling(tmp_path):
    readme = "# t\n\n## Setup\n\n```bash\nexport GEMINI_API_KEY=your_key_here\npip install <package>\n```\n"
    plan = extract_plan(project(tmp_path, readme, {}))
    assert [s.command for s in plan.steps] == ["export GEMINI_API_KEY=your_key_here", "pip install <package>"]


def test_ai_plans_get_placeholder_skips_too(tmp_path):
    from firstrun.models import Plan, Step
    from firstrun.readme import apply_directives

    plan = Plan(steps=[Step(1, "pip install -r requirements.txt"),
                       Step(2, "python main.py <your-file>", kind="run", line=9)])
    out = apply_directives(plan, "# t\n")
    assert [s.command for s in out.steps] == ["pip install -r requirements.txt"]
    assert out.skipped[0].reason == "needs your own input (placeholder `<your-file>`)"


LOG_README = f"""# Stacktrace copilot

## Install

```bash
{VENV_STEPS}pip install -r requirements.txt
```

## How to Run

```bash
python main.py --file examples/sample.log
python main.py --file examples/sample.log --json
```
"""


def test_missing_input_file_points_readme_at_closest_file(tmp_path):
    proj = project(tmp_path, LOG_README, {"requirements.txt": "", "main.py": "print(1)\n",
                                          "examples/sample_stacktrace.log": "Traceback\n",
                                          "examples/notes.txt": "x\n"})
    plan = extract_plan(proj)
    out = ("usage: main.py [-h] --file FILE [--json]\nmain.py: error: Could not read input file: "
           "[Errno 2] No such file or directory: 'examples/sample.log'\n")
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py --file examples/sample.log", out, exit_code=2))
    assert d.category == "missing_file" and d.confidence == "medium"
    assert "examples/sample_stacktrace.log" in d.summary
    check_edits(proj, d)
    text = (proj / "README.md").read_text()
    assert text.count("python main.py --file examples/sample_stacktrace.log") == 2
    assert "examples/sample.log" not in text


def test_missing_input_file_without_candidate(tmp_path):
    readme = LOG_README.replace("--file examples/sample.log", "--input invoice.json")
    proj = project(tmp_path, readme, {"requirements.txt": "", "main.py": "print(1)\n", "config.json": "{}\n"})
    plan = extract_plan(proj)
    out = ("Traceback (most recent call last):\n  File \"/work/main.py\", line 9, in <module>\n"
           "FileNotFoundError: [Errno 2] No such file or directory: 'invoice.json'\n")
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py --input invoice.json", out))
    assert d.category == "missing_file" and d.confidence == "high"
    assert d.edits == []  # config.json is not a plausible stand-in for invoice.json
    assert "`invoice.json`" in d.summary and "Commit the file" in d.explanation


def test_loose_file_not_found_message_counts_when_it_is_an_argument(tmp_path):
    readme = PDF_README.replace("path/to/your/document.pdf", "report.pdf")
    proj = project(tmp_path, readme, {"requirements.txt": "", "main.py": "print(1)\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py report.pdf", "Error: File not found: report.pdf\n"))
    assert d.category == "missing_file" and "`report.pdf`" in d.summary
    other = rules.diagnose(proj, plan, fail_at(plan, "python main.py report.pdf", "Error: File not found: settings.yaml\n"))
    assert other is None


GIT_TRACE = (
    "Traceback (most recent call last):\n"
    '  File "/work/main.py", line 4, in <module>\n'
    "    run()\n"
    '  File "/work/sentinel/diff.py", line 12, in run\n'
    '    subprocess.run(["git", "diff"], check=True)\n'
    '  File "/usr/local/lib/python3.12/subprocess.py", line 1955, in _execute_child\n'
    "    raise child_exception_type(errno_num, err_msg, err_filename)\n"
    "FileNotFoundError: [Errno 2] No such file or directory: 'git'\n"
)


def test_missing_program_is_a_platform_issue_not_a_missing_file(tmp_path):
    files = {"requirements.txt": "", "main.py": "print(1)\n", "sentinel/diff.py": "import subprocess\n"}
    proj = project(tmp_path, README_PY, files)
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", GIT_TRACE))
    assert d.category == "platform_issue"
    assert d.summary == "The code runs `git`, a system tool the README does not list as a prerequisite."
    assert ("sentinel/diff.py", 12) in [(e.file, e.line) for e in d.evidence]
    assert d.edits == []


def test_missing_program_added_to_prerequisites(tmp_path):
    readme = "# t\n\n## Prerequisites\n\n- Python 3.10+\n- pip\n\n" + README_PY.split("\n", 1)[1]
    proj = project(tmp_path, readme, {"requirements.txt": "", "main.py": "print(1)\n", "sentinel/diff.py": "x = 1\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", GIT_TRACE))
    check_edits(proj, d)
    assert "- pip\n- `git` installed and on your PATH\n" in (proj / "README.md").read_text()


def test_tool_listed_in_prerequisites_is_an_environment_gap(tmp_path):
    readme = "# t\n\n## Prerequisites\n\n- Node.js 20+\n\n## Install\n\n```bash\nnpm install\n```\n"
    proj = project(tmp_path, readme, {"package.json": "{}\n"})
    plan = extract_plan(proj)
    out = "/firstrun/step_1.sh: line 1: npm: command not found\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "npm install", out, exit_code=127))
    assert d.category == "platform_issue" and d.edits == []
    assert "lists npm as a prerequisite, but the sandbox image does not include it" in d.summary


GATEKEEPER_ENV = "GOOGLE_API_KEY=\nGITHUB_TOKEN=\nGEMINI_API_KEY=\nOPENAI_API_KEY=\n"
GITHUB_401 = (
    "Reviewing https://github.com/gdgcblr/open-source-agents/pull/12 (Gemini + deterministic)\n"
    "Traceback (most recent call last):\n"
    '  File "/work/gatekeeper/source.py", line 60, in github_api\n'
    "    with urllib.request.urlopen(req) as resp:\n"
    "urllib.error.HTTPError: HTTP Error 401: Unauthorized\n"
)


def test_credentials_rank_the_failing_service_first(tmp_path):
    proj = project(tmp_path, README_PY, {
        "requirements.txt": "", ".env.example": GATEKEEPER_ENV, "main.py": "print(1)\n",
        "gatekeeper/source.py": "import os\nTOKEN = os.getenv('GITHUB_TOKEN')\n",
        "tests/test_checks.py": "import os\nos.environ['WEATHER_API_KEY']\n",
        "evals/cases.py": "import os\nos.getenv('WEATHER_API_KEY')\n",
    })
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python main.py", GITHUB_401))
    # github is nearest the error, Gemini is mentioned earlier in the output, then the rest
    assert d.blocked and d.missing_env == ["GITHUB_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"]
    assert "WEATHER_API_KEY" not in d.summary and d.edits == []
    assert "(GITHUB_TOKEN, GEMINI_API_KEY, GOOGLE_API_KEY and 1 more)" in d.summary
    assert not any("WEATHER_API_KEY" in h for h in rules.static_hints(proj))


def test_credentials_gemini_before_google(tmp_path):
    out = ("google.genai.errors.ClientError: 400 INVALID_ARGUMENT. {'error': {'message': "
           "'API key not valid. Please pass a valid API key.'}}\n")
    names = rules.detect_credentials(out, project(tmp_path, README_PY, {".env.example": GATEKEEPER_ENV}))
    assert names[:2] == ["GEMINI_API_KEY", "GOOGLE_API_KEY"]


def test_credentials_named_in_output_come_first_without_unrelated_keys(tmp_path):
    proj = project(tmp_path, README_PY, {".env.example": GATEKEEPER_ENV})
    assert rules.detect_credentials("KeyError: 'OPENAI_API_KEY'\n", proj) == ["OPENAI_API_KEY"]


def test_credentials_fall_back_to_the_service_usual_name(tmp_path):
    out = "requests.exceptions.HTTPError: 401 Client Error: Unauthorized for url: https://api.github.com/user\n"
    assert rules.detect_credentials(out, project(tmp_path, README_PY, {})) == ["GITHUB_TOKEN"]


# round 2: expected exits, host level tools

LINT_README = f"""# Schema lint

## Install

```bash
{VENV_STEPS}pip install -r requirements.txt
```

## How to Run

Lint the broken example:

```bash
python -m schema_lint examples/broken.json
```

```text
examples/broken.json
  error   S001   missing additionalProperties
2 errors, 5 warnings
```

Lint every target:

```bash
python -m schema_lint examples/broken.json --target all
```

```bash
python -m pytest
```
"""
LINT_OUT = "examples/broken.json\n  error   S001   missing additionalProperties\n\n2 errors, 5 warnings, 1 info\n"


def test_expected_exit_rule_marks_every_block_of_the_tool(tmp_path):
    proj = project(tmp_path, LINT_README, {"requirements.txt": "", "schema_lint/__main__.py": "print(1)\n"})
    plan = extract_plan(proj)
    d = rules.diagnose(proj, plan, fail_at(plan, "python -m schema_lint examples/broken.json", LINT_OUT))
    assert d.category == "undocumented_step" and "exits 1 on purpose" in d.summary
    check_edits(proj, d)
    text = (proj / "README.md").read_text()
    assert text.count("<!-- firstrun: expect-exit 1 -->") == 2  # both lint blocks, not pytest
    patched = extract_plan(proj)
    by_cmd = {s.command: s.expect_exit for s in patched.steps}
    assert by_cmd["python -m schema_lint examples/broken.json"] == 1
    assert by_cmd["python -m schema_lint examples/broken.json --target all"] == 1
    assert by_cmd["python -m pytest"] is None


def test_expected_exit_needs_matching_documented_output(tmp_path):
    proj = project(tmp_path, LINT_README, {"requirements.txt": ""})
    plan = extract_plan(proj)
    other = "Error: could not connect to the schema registry\n"
    d = rules.diagnose(proj, plan, fail_at(plan, "python -m schema_lint examples/broken.json", other))
    assert d is None or d.category != "undocumented_step"
    trace = "Traceback (most recent call last):\n" + LINT_OUT
    d = rules.diagnose(proj, plan, fail_at(plan, "python -m schema_lint examples/broken.json", trace))
    assert d is None or "on purpose" not in d.summary


def test_console_transcript_counts_as_documented_output():
    from firstrun.readme import documented_output

    text = "# t\n\n```console\n$ lint a.json\na.json\n  2 errors\n$ lint b.json\nok\n```\n"
    assert documented_output(text, 4) == "a.json\n  2 errors"
    assert documented_output(text, 7) == "ok"
    assert documented_output(text, 1) is None


@pytest.mark.parametrize("command, tool", [
    ("docker compose -f lab/docker-compose.yml up -d --build", "docker"),
    ("kubectl apply -f k8s/", "kubectl"),
    ("minikube start", "minikube"),
])
def test_host_level_tools_block_the_run(tmp_path, command, tool):
    readme = f"# Lab\n\n## How to Run\n\n```bash\n{command}\n```\n"
    proj = project(tmp_path, readme, {})
    plan = extract_plan(proj)
    out = f"/firstrun/step_1.sh: line 1: {tool}: command not found\n"
    d = rules.diagnose(proj, plan, fail_at(plan, command.split()[0], out, exit_code=127))
    assert d.category == "platform_issue" and d.blocked
    assert d.summary == f"Needs {tool} inside the sandbox, which FirstRun does not provide."

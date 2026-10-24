import shutil
from pathlib import Path

import pytest

from firstrun.readme import (
    command_word,
    extract_plan,
    locate_line,
    parse_code_blocks,
    strip_comment,
)

TEMPLATE = Path(__file__).resolve().parents[3] / "template"


def write_project(tmp_path: Path, readme: str, **files: str) -> Path:
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def template_project(tmp_path):
    if not (TEMPLATE / "README.md").is_file():
        pytest.skip("repository template not available")
    shutil.copy(TEMPLATE / "README.md", tmp_path / "README.md")
    shutil.copy(TEMPLATE / ".env.example", tmp_path / ".env.example")
    return tmp_path


def commands(plan):
    return [s.command for s in plan.steps]


def test_template_readme(template_project):
    plan = extract_plan(template_project)
    cmds = commands(plan)
    assert cmds[:3] == ["python -m venv .venv", "source .venv/bin/activate", "pip install -r requirements.txt"]
    assert "cp .env.example .env" in cmds
    assert "npm start" in cmds and "npm install" in cmds
    assert "pytest" in cmds
    reasons = {s.command: s.reason for s in plan.skipped}
    assert "windows" in reasons[".venv\\Scripts\\activate"]
    assert "cd agents/<project-slug>" in reasons
    # example input/output blocks are not commands
    assert not any("Analysis completed" in c or "Analyze the repository" in c for c in cmds)
    assert plan.expected_output.startswith("Analysis completed:")
    assert plan.readme_path == "README.md" and plan.engine == "rules"
    npm_start = next(s for s in plan.steps if s.command == "npm start")
    assert npm_start.long_running and npm_start.kind == "run"


def test_template_line_numbers(template_project):
    text = (template_project / "README.md").read_text()
    lines = text.splitlines()
    for step in extract_plan(template_project).steps:
        assert step.command.splitlines()[0] in lines[step.line - 1]


def test_prompts_continuations_and_comments(tmp_path):
    readme = """# Demo

## Install

```console
$ pip install -r requirements.txt   # takes a minute
Collecting rich
Successfully installed rich-13.0
$ python main.py \\
>   --name "Ada # Lovelace"
Hello Ada
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    assert commands(plan) == [
        "pip install -r requirements.txt",
        'python main.py \\\n--name "Ada # Lovelace"',
    ]
    assert plan.steps[0].line == 6
    assert plan.steps[0].kind == "setup"
    assert plan.steps[1].kind == "run"


def test_clone_and_cd_are_skipped(tmp_path):
    readme = """# Tool

```bash
git clone https://github.com/someone/cool-tool.git
cd cool-tool
cd src
pip install -e .
```
"""
    project = write_project(tmp_path, readme, **{"src/app.py": "print('hi')\n"})
    plan = extract_plan(project)
    assert commands(plan) == ["cd src", "pip install -e ."]
    skipped = [s.command for s in plan.skipped]
    assert skipped[0].startswith("git clone")
    assert "cd cool-tool" in skipped


def test_cd_and_compound(tmp_path):
    readme = """```bash
cd agents/my-agent && pip install -r requirements.txt
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    assert commands(plan) == ["pip install -r requirements.txt"]
    assert plan.skipped[0].command == "cd agents/my-agent"


def test_blank_language_blocks(tmp_path):
    readme = """## Usage

```
python app.py --city Pune
```

## Example Output

```
Weather in Pune: 31C, sunny
python is great
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    # the second block is output, but "python is great" starts with a known word,
    # so only blocks under an Output heading are treated as documented output
    assert commands(plan)[0] == "python app.py --city Pune"
    assert plan.expected_output.startswith("Weather in Pune")


def test_ignored_languages(tmp_path):
    readme = """```python
import os
print(os.getcwd())
```

```env
GEMINI_API_KEY=your_key_here
```

```bash
python main.py
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    assert commands(plan) == ["python main.py"]


def test_long_running_and_server_scripts(tmp_path):
    readme = """## Run

```bash
streamlit run app.py
python server.py
python cli.py
```
"""
    project = write_project(
        tmp_path,
        readme,
        **{"server.py": "import uvicorn\nuvicorn.run('x:app')\n", "cli.py": "print('done')\n"},
    )
    plan = extract_plan(project)
    flags = {s.command: s.long_running for s in plan.steps}
    assert flags == {"streamlit run app.py": True, "python server.py": True, "python cli.py": False}


def test_windows_heading_and_comment_context(tmp_path):
    readme = """## Setup

```bash
# On Windows (PowerShell):
copy .env.example .env
py -m venv .venv
# On Linux or macOS:
cp .env.example .env
```

### Windows

```bash
setup.bat
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    assert commands(plan) == ["cp .env.example .env"]
    assert all("windows" in s.reason for s in plan.skipped)
    assert plan.steps[0].kind == "configure"


def test_heredoc_is_one_step(tmp_path):
    readme = """```bash
cat > .env <<EOF
MODEL=gemini
EOF
python main.py
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    assert commands(plan) == ["cat > .env <<EOF\nMODEL=gemini\nEOF", "python main.py"]


def test_duplicates_and_required_env(tmp_path):
    readme = """## Quick start
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=<your-key>
python main.py
```
## Installation
```bash
pip install -r requirements.txt
```
"""
    project = write_project(tmp_path, readme, **{".env.example": "GEMINI_API_KEY=\nLOG_LEVEL=info\n"})
    plan = extract_plan(project)
    assert commands(plan) == ["pip install -r requirements.txt", "export GEMINI_API_KEY=<your-key>", "python main.py"]
    assert plan.skipped[-1].reason == "duplicate of step 1"
    assert plan.required_env == ["GEMINI_API_KEY"]
    assert any("placeholder" in n for n in plan.notes)


def test_documented_prerequisite_is_provided(tmp_path):
    readme = """## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
uv run main.py
```
"""
    plan = extract_plan(write_project(tmp_path, readme))
    assert commands(plan) == ["pip install uv", "uv sync", "uv run main.py"]
    assert plan.steps[0].provided_by_firstrun and plan.steps[0].kind == "prerequisite"


def test_undocumented_tool_is_not_provided(tmp_path):
    plan = extract_plan(write_project(tmp_path, "```bash\nuv sync\n```\n"))
    assert commands(plan) == ["uv sync"]


def test_no_readme(tmp_path):
    plan = extract_plan(tmp_path)
    assert plan.steps == [] and plan.notes


def test_helpers():
    assert strip_comment("pip install x  # note") == "pip install x"
    assert strip_comment("echo '#not a comment'") == "echo '#not a comment'"
    assert command_word("FOO=1 sudo python x.py") == "python"
    text = "a\n  $ pip install -r requirements.txt\n"
    assert locate_line(text, "pip install -r requirements.txt") == 2
    blocks = parse_code_blocks("# H\n\n   ```bash\n   ls\n   ```\n")
    assert blocks[0]["lang"] == "bash" and blocks[0]["lines"] == [(4, "ls")]
    assert blocks[0]["section"] == "H" and blocks[0]["start"] == 3 and blocks[0]["end"] == 5


def test_author_directives_skip_and_long_running(tmp_path):
    from firstrun.readme import extract_plan

    (tmp_path / "README.md").write_text(
        "# demo\n\n```bash\npip install -r requirements.txt\n```\n\n"
        "<!-- firstrun: skip needs a GitHub login -->\n```bash\ngh auth status\n```\n\n"
        "<!-- firstrun: long-running -->\n\n```bash\npython serve_it.py\n```\n\n"
        "```bash\npython -m myapp.web --port 9000\n```\n"
    )
    plan = extract_plan(tmp_path)
    assert [s.command for s in plan.steps] == [
        "pip install -r requirements.txt", "python serve_it.py", "python -m myapp.web --port 9000",
    ]
    assert [s.index for s in plan.steps] == [1, 2, 3]
    assert plan.steps[1].long_running and plan.steps[2].long_running
    skipped = [k for k in plan.skipped if k.command == "gh auth status"]
    assert skipped and "needs a GitHub login" in skipped[0].reason and skipped[0].line == 9


def test_words_containing_mac_do_not_mean_macos(tmp_path):
    from firstrun.readme import extract_plan

    (tmp_path / "README.md").write_text(
        "# demo\n\n## Runs on the author's machine only\n\n```bash\npython main.py\n```\n\n"
        "## macOS\n\n```bash\nbrew install jq\n```\n"
    )
    plan = extract_plan(tmp_path)
    assert [s.command for s in plan.steps] == ["python main.py"]
    assert plan.skipped[0].reason.startswith("macOS-only")


def test_expect_exit_directive(tmp_path):
    from firstrun.readme import extract_plan

    (tmp_path / "README.md").write_text(
        "# lint\n\n<!-- firstrun: expect-exit 2 -->\n```bash\npython -m lint broken.json\n```\n\n"
        "```bash\npython -m lint ok.json\n```\n"
    )
    plan = extract_plan(tmp_path)
    assert [(s.command, s.expect_exit) for s in plan.steps] == [
        ("python -m lint broken.json", 2), ("python -m lint ok.json", None),
    ]

import json
import subprocess
from pathlib import Path

import pytest

from submission_linter import llm_review
from submission_linter.checks import lint_project
from submission_linter.cli import main
from submission_linter.secrets_scan import scan_text

GOOD_README = """# Quote Bot

> Posts a quote of the day.

## Overview
### Problem Statement & Intended Users
- **Problem**: People want a daily quote without opening a browser.
- **Intended Users**: Anyone with a terminal.

## Technical Stack
- Python 3.11, requests

## Architecture & Data Flow
Input goes to main.py which calls the API and prints the result.

## Prerequisites
- Python 3.10+ and pip

## Installation & Setup
1. `pip install -r requirements.txt`
2. `cp .env.example .env`

## Configuration & Environment Variables
| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `QUOTE_API_URL` | No | `https://example.org` | Quote endpoint |

## How to Run
```bash
python main.py
```

## Example Input & Output
Run `python main.py` and a single quote line is printed.

## How to Test
```bash
pytest
```

## Known Limitations
- Needs network access; no retry logic.

## Security & Privacy Considerations
- No credentials needed. No data leaves the machine except the API request.

## Future Improvements
- [ ] Cache quotes.

## License
This project is contributed under the repository's open-source license.
"""

MAIN_PY = 'import os\nimport requests\n\nURL = os.getenv("QUOTE_API_URL", "https://example.org")\nprint(requests.get(URL).text)\n'


def make_project(root: Path, category="tools", slug="quote-bot", **overrides) -> Path:
    files = {
        "README.md": GOOD_README,
        ".env.example": "QUOTE_API_URL=https://example.org\n",
        ".gitignore": ".env\n.venv/\n__pycache__/\n",
        "requirements.txt": "requests>=2.0\npytest\n",
        "main.py": MAIN_PY,
        "test_main.py": "def test_ok():\n    assert True\n",
    }
    files.update(overrides)
    proj = root / category / slug
    for name, content in files.items():
        if content is None:
            continue
        (proj / name).parent.mkdir(parents=True, exist_ok=True)
        (proj / name).write_text(content)
    return proj


def codes(path, **kw):
    report, _ = lint_project(path, **kw)
    return {f.code for f in report.findings}, report


def test_good_project_has_no_errors(tmp_path):
    c, report = codes(make_project(tmp_path))
    assert report.errors == 0, report.to_dict()
    assert report.warnings == 0, report.to_dict()  # only the SCP000 info note is allowed


@pytest.mark.parametrize("slug,code", [("My_Tool", "LOC002"), ("demo", "LOC003")])
def test_bad_names(tmp_path, slug, code):
    c, _ = codes(make_project(tmp_path, slug=slug))
    assert code in c


def test_wrong_category(tmp_path):
    c, _ = codes(make_project(tmp_path, category="misc"))
    assert "LOC001" in c


def test_missing_files(tmp_path):
    c, _ = codes(make_project(tmp_path, **{".env.example": None, "requirements.txt": None}))
    assert {"FIL001", "FIL002"} <= c


def test_untouched_template_is_flagged(tmp_path):
    tmpl = "# [Project Name]\n\n> [One-sentence summary of what this project does and the value it provides.]\n"
    c, _ = codes(make_project(tmp_path, **{"README.md": tmpl}))
    assert {"DOC001", "DOC003"} <= c


def test_empty_section_warns(tmp_path):
    readme = GOOD_README.replace("- Needs network access; no retry logic.", "")
    c, _ = codes(make_project(tmp_path, **{"README.md": readme}))
    assert "DOC004" in c


def test_fake_secret_detected_and_redacted(tmp_path):
    fake = "AKIA" + "ABCDEFGHIJKLMNOP"  # built at runtime so this file is clean
    proj = make_project(tmp_path, **{"main.py": MAIN_PY + f'KEY = "{fake}"\n'})
    report, _ = lint_project(proj)
    hits = [f for f in report.findings if f.code == "SEC001"]
    assert hits and hits[0].line == 6
    assert fake not in json.dumps(report.to_dict())


def test_generic_secret_and_allow_marker():
    value = "q8Zr" + "T3vL9xWm" + "B2nK7pYd"
    assert scan_text(f'API_TOKEN = "{value}"\n')
    assert not scan_text(f'API_TOKEN = "{value}"  # lint:allow-secret\n')
    assert not scan_text('API_KEY = "your-api-key-here"\n')
    assert not scan_text('API_KEY = os.environ["API_KEY"]\n')


def test_env_file_committed(tmp_path):
    proj = make_project(tmp_path, **{".env": "FOO=bar\n"})
    c, _ = codes(proj)
    assert "GIT005" in c or "GIT002" in c


def test_env_vars_must_be_documented(tmp_path):
    main_py = MAIN_PY + 'TOKEN = os.environ["NEW_SETTING"]\n'
    c, _ = codes(make_project(tmp_path, **{"main.py": main_py}))
    assert {"ENV001", "ENV002"} <= c


def test_run_command_pointing_to_missing_file(tmp_path):
    readme = GOOD_README.replace("python main.py\n```", "python app.py --query hi\n```", 1)
    c, report = codes(make_project(tmp_path, **{"README.md": readme}))
    assert "RUN001" in c
    assert any("app.py" in f.message for f in report.findings)


def test_npm_script_missing(tmp_path):
    readme = GOOD_README.replace("python main.py\n```", "npm start\n```", 1)
    c, _ = codes(make_project(tmp_path, **{"README.md": readme, "package.json": '{"scripts": {}}'}))
    assert "RUN002" in c


def test_undeclared_python_dependency(tmp_path):
    c, report = codes(make_project(tmp_path, **{"main.py": "import numpy\nimport yaml\nprint(1)\n"}))
    msgs = [f.message for f in report.findings if f.code == "DEP001"]
    assert any("numpy" in m for m in msgs) and any("yaml" in m for m in msgs)


def test_stdlib_and_local_imports_ok(tmp_path):
    c, _ = codes(make_project(tmp_path, **{"main.py": "import os, json\nimport helpers\n", "helpers.py": "x=1\n"}))
    assert "DEP001" not in c


def test_pytest_documented_without_tests(tmp_path):
    c, _ = codes(make_project(tmp_path, **{"test_main.py": None}))
    assert "TST001" in c


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"], "HOME": str(cwd)})


def test_scope_flags_changes_outside_project(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "README.md").write_text("index\n")
    (tmp_path / "ROOT.md").write_text("root\n")
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "init")
    git(tmp_path, "checkout", "-b", "feat/quote-bot")
    proj = make_project(tmp_path)
    (tmp_path / "ROOT.md").write_text("changed\n")
    (tmp_path / "tools" / "README.md").write_text("index + row\n")  # allowed
    c, report = codes(proj, base="main")
    scope = [f for f in report.findings if f.code == "SCP001"]
    assert scope and "ROOT.md" in scope[0].message and "tools/README.md" not in scope[0].message


def test_scope_clean(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "README.md").write_text("index\n")
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "init")
    c, _ = codes(make_project(tmp_path), base="main")
    assert "SCP001" not in c


def test_gitignored_files_are_not_scanned_in_git_repo(tmp_path):
    proj = make_project(tmp_path)
    git(tmp_path, "init", "-b", "main")
    (proj / ".env").write_text("OPENAI_API_KEY=" + "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7\n")
    c, _ = codes(proj, base="main")
    assert "SEC001" not in c and "GIT002" not in c  # .env is ignored by .gitignore


def test_llm_review_with_fake_transport(tmp_path, monkeypatch):
    proj = make_project(tmp_path)
    _, ctx = lint_project(proj)
    seen = {}

    def fake(url, headers, payload, timeout):
        seen["url"], seen["payload"] = url, payload
        body = {"findings": [{"severity": "warn", "title": "Undisclosed network call",
                              "detail": "main.py calls an external URL.", "evidence": "main.py:5"},
                             {"severity": "error", "title": "x", "detail": "y", "evidence": ""}]}
        return {"choices": [{"message": {"content": "```json\n" + json.dumps(body) + "\n```"}}]}

    findings = llm_review.review(proj, ctx["listing"], ctx["readme"], ctx["tainted"], transport=fake)
    assert seen["url"].endswith("/chat/completions")
    assert [f.severity for f in findings] == ["warn", "info"]  # LLM can never emit 'error'
    assert "=== main.py ===" in seen["payload"]["messages"][1]["content"]


def test_llm_never_sends_tainted_or_env_files(tmp_path):
    fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
    proj = make_project(tmp_path, **{"leaky.py": f'K = "{fake_key}"\n', ".env": "A=b\n"})
    _, ctx = lint_project(proj)
    prompt, sent = llm_review.build_prompt(ctx["project"], ctx["listing"], ctx["readme"], ctx["tainted"])
    assert fake_key not in prompt
    assert all(name not in {"leaky.py", ".env"} for name, _ in sent)


def test_llm_endpoint_down_is_not_fatal(tmp_path):
    proj = make_project(tmp_path)
    _, ctx = lint_project(proj)

    def boom(*a, **k):
        raise OSError("connection refused")

    findings = llm_review.review(proj, ctx["listing"], ctx["readme"], ctx["tainted"], transport=boom)
    assert findings and findings[0].code == "LLM000" and findings[0].severity == "info"


def test_cli_exit_codes_and_json(tmp_path, capsys):
    good = make_project(tmp_path)
    assert main([str(good), "--json", "--base", "main"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["errors"] == 0
    bad = make_project(tmp_path, slug="demo")
    assert main([str(bad), "--no-color"]) == 1
    assert main([str(tmp_path / "nope")]) == 2


def test_env_vars_read_only_by_tests_are_ignored(tmp_path):
    proj = make_project(tmp_path, **{"tests/test_env.py": 'import os\nX = os.getenv("ONLY_IN_TESTS")\n'})
    report, _ = lint_project(proj)
    assert not any("ONLY_IN_TESTS" in f.message for f in report.findings)

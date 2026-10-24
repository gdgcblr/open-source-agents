"""The sample projects must be broken in exactly the way examples/README.md says."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SAMPLES = {
    "quote-of-the-day": "main.py",
    "standup-notes": "src/summarize.py",
    "gemini-haiku": "haiku.py",
}


def documented_output(readme: Path) -> str:
    lines = readme.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().lower() == "## example output")
    fence = next(i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("```"))
    end = next(i for i in range(fence + 1, len(lines)) if lines[i].strip().startswith("```"))
    return "\n".join(lines[fence + 1:end])


def python(args, cwd, env=None):
    # -S and -E keep the host's site-packages and PYTHON* vars out, so only the stdlib imports
    return subprocess.run(
        [sys.executable, "-S", "-E", *args],
        cwd=cwd,
        env=env if env is not None else {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_with_stubs(cwd, stubs, script, *argv):
    code = (
        "import runpy, sys; "
        f"sys.path.insert(0, {str(stubs)!r}); "
        f"sys.argv = {[script, *argv]!r}; "
        f"runpy.run_path({script!r}, run_name='__main__')"
    )
    return python(["-c", code], cwd)


@pytest.fixture
def copy_sample(tmp_path):
    def _copy(name):
        return Path(shutil.copytree(EXAMPLES / name, tmp_path / name))
    return _copy


@pytest.fixture
def stubs(tmp_path):
    root = tmp_path / "stubs"
    root.mkdir()
    (root / "colorama.py").write_text(
        "class Fore:\n    CYAN = ''\n\nclass Style:\n    BRIGHT = ''\n    RESET_ALL = ''\n"
    )
    return root


@pytest.mark.parametrize("name,entry", SAMPLES.items())
def test_sample_structure(name, entry):
    sample = EXAMPLES / name
    assert (sample / "README.md").is_file()
    assert (sample / "requirements.txt").is_file()
    assert (sample / entry).is_file()
    assert not [p for p in sample.rglob(".env") if p.is_file()], "samples must not ship a .env"
    readme = (sample / "README.md").read_text(encoding="utf-8")
    assert "python -m venv .venv" in readme
    assert ".venv\\Scripts\\activate" in readme
    assert "source .venv/bin/activate" in readme
    assert "pip install -r requirements.txt" in readme
    assert "## Example Output" in readme


def test_no_em_or_en_dashes_in_samples():
    for path in EXAMPLES.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert chr(0x2014) not in text and chr(0x2013) not in text, path


def test_quote_forgets_python_dotenv(copy_sample, stubs):
    sample = copy_sample("quote-of-the-day")
    assert "dotenv" not in (sample / "requirements.txt").read_text().lower()
    assert "from dotenv import load_dotenv" in (sample / "main.py").read_text()

    result = run_with_stubs(sample, stubs, "main.py", "--day", "3")
    assert result.returncode != 0
    assert "No module named 'dotenv'" in result.stderr


def test_quote_works_once_dotenv_is_installed(copy_sample, stubs):
    sample = copy_sample("quote-of-the-day")
    (stubs / "dotenv.py").write_text("def load_dotenv(*args, **kwargs):\n    return False\n")

    result = run_with_stubs(sample, stubs, "main.py", "--day", "3")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == documented_output(sample / "README.md").strip()


def test_standup_documented_command_points_at_missing_file(copy_sample):
    sample = copy_sample("standup-notes")
    assert "python summarize.py notes.txt" in (sample / "README.md").read_text()
    assert not (sample / "summarize.py").exists()

    result = python(["summarize.py", "notes.txt"], sample)
    assert result.returncode != 0
    assert "can't open file" in result.stderr


def test_standup_real_path_prints_documented_output(copy_sample):
    sample = copy_sample("standup-notes")
    result = python(["src/summarize.py", "notes.txt"], sample)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == documented_output(sample / "README.md").strip()


def test_haiku_without_key_stops_and_names_the_variable(copy_sample):
    sample = copy_sample("gemini-haiku")
    result = python(["haiku.py", "monsoon"], sample)
    assert result.returncode != 0
    assert "GEMINI_API_KEY" in result.stderr
    assert result.stdout == "", "must never print a haiku it did not get from Gemini"


def test_haiku_with_placeholder_key_is_still_blocked(copy_sample):
    sample = copy_sample("gemini-haiku")
    shutil.copy(sample / ".env.example", sample / ".env")  # what the README tells you to do
    result = python(["haiku.py", "monsoon"], sample)
    assert result.returncode != 0
    assert "GEMINI_API_KEY" in result.stderr
    assert result.stdout == ""

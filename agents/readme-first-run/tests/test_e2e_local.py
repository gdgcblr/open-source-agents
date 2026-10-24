"""Full pipeline on the bundled samples with the local sandbox and offline rules.

These run real commands (venv creation, pip install) so they take a little while, and the
quote-of-the-day check needs PyPI for python-dotenv. Skip them with: pytest -m "not e2e"
"""

import shutil
from pathlib import Path

import pytest

from firstrun.agent import Settings, run_check

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash"),
]


def check(name, tmp_path, **kw):
    settings = Settings(sandbox="local", offline=True, out_dir=tmp_path / "runs", watch_seconds=5, **kw)
    return run_check(str(EXAMPLES / name), settings)


def test_quote_of_the_day_missing_dependency_is_fixed(tmp_path):
    report, run_dir = check("quote-of-the-day", tmp_path)
    assert report.verdict == "fixed", report.headline
    failed = report.documented_run.failed_step
    assert "python main.py" in failed.step.command
    assert "dotenv" in failed.output
    assert "+python-dotenv" in report.final_diff
    assert report.rounds[-1].verification.status == "passed"
    assert report.output_check and report.output_check["verdict"] == "matches"
    assert (run_dir / "fix.patch").exists()


def test_standup_notes_wrong_path_is_fixed(tmp_path):
    report, _ = check("standup-notes", tmp_path)
    assert report.verdict == "fixed", report.headline
    assert "src/summarize.py" in report.final_diff
    assert report.rounds[-1].diagnosis.category == "wrong_command"


def test_gemini_haiku_is_blocked_without_a_key(tmp_path):
    report, run_dir = check("gemini-haiku", tmp_path)
    assert report.verdict == "blocked", report.headline
    assert "GEMINI_API_KEY" in report.headline
    # it must not have produced anything that looks like a haiku
    assert not (run_dir / "fix.patch").exists() or "haiku" not in report.final_diff.lower()

import random

from evals import fixtures as fx
from prcheck import markdown, secret_patterns
from prcheck.context import build_context
from prcheck.models import Severity, Status
from prcheck.registry import CheckSpec
from prcheck.rules import load_rules
from prcheck.runner import run, run_check, summarize


def test_headings_inside_code_fences_are_ignored():
    parsed = markdown.parse("## Real\n```\n## Not a heading\n```\n## Also real\n")
    assert [s.title for s in parsed.sections] == ["Real", "Also real"]


def test_mask_hides_most_of_the_value():
    assert secret_patterns.mask("abcdefghijklmnop") == "abcd...nop"
    assert secret_patterns.mask("short") == "*****"


def test_redact_replaces_every_secret():
    rng = random.Random(1)
    text = f"key={fx.fake_google_key(rng)}\nother line\ntoken {fx.fake_github_token(rng)}"
    redacted, count = secret_patterns.redact(text)
    assert count == 2
    assert secret_patterns.scan(redacted) == []
    assert "other line" in redacted


def test_crashing_check_is_reported_not_passed(tmp_path):
    project = fx.build_repo(tmp_path)
    ctx = build_context(project, load_rules(), use_git=False)

    def boom(_ctx):
        raise RuntimeError("bug")

    result = run_check(CheckSpec("Z9", "test", "crashes", Severity.ERROR, "test", boom), ctx)
    assert result.status is Status.CRASH
    summary = summarize([result], strict=False)
    assert summary.crashed == 1 and not summary.ready


def test_strict_mode_blocks_on_warnings(tmp_path):
    project = fx.build_repo(tmp_path, files={".gitignore": None})  # S4 is a warning
    relaxed, _ = run(project, use_git=False)
    strict, _ = run(project, use_git=False, strict=True)
    assert relaxed.summary.ready
    assert not strict.summary.ready


def test_runs_outside_the_repository(tmp_path):
    project = tmp_path / "standalone-tool"
    fx.write_files(project, fx.GOOD_FILES)
    report, _ = run(project, use_git=False)
    statuses = {r.id: r.status for r in report.checks}
    assert statuses["S1"] is Status.SKIP
    assert report.template_source == "bundled"
    assert report.summary.ready

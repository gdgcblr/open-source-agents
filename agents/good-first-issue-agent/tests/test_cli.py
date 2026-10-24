import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import REPO_META, FakeResponse, FakeSession, gh_issue

from good_first_issue_agent import cli
from good_first_issue_agent.errors import AIUnavailableError, RateLimitError
from good_first_issue_agent.models import AIResult
from good_first_issue_agent.output import render_json, render_text

PROJECT = Path(__file__).resolve().parents[1]
GOOD = "Expected behaviour: should print the file name.\n\nSteps to reproduce\n1. run\n2. see\n\n```\nerr\n```"


def args(*argv):
    return cli.build_parser().parse_args(list(argv))


def gh_session(issues, meta=None):
    return FakeSession(routes={"/repos/o/r": FakeResponse(200, meta or REPO_META)},
                       responses=[FakeResponse(200, issues)])


def test_help_runs_as_module():
    out = subprocess.run([sys.executable, "-m", "good_first_issue_agent", "--help"],
                         cwd=PROJECT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "--repo" in out.stdout and "--source" in out.stdout and "--ai" in out.stdout


@pytest.mark.parametrize("argv", [
    ["--repo", "o/r", "--limit", "0"],
    ["--repo", "o/r", "--limit", "500"],
    ["--repo", "o/r", "--top", "0"],
    ["--repo", "o/r", "--timeout", "0"],
    ["--repo", "o/r", "--format", "xml"],
    ["--source", "jira"],
])
def test_invalid_options_exit_2(argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_malformed_repo_exit_2(capsys):
    assert cli.main(["--repo", "not a repo"]) == 2
    assert "Error:" in capsys.readouterr().err


def test_missing_repo(capsys):
    assert cli.main([]) == 2
    assert "--repo is required" in capsys.readouterr().err


def test_ranked_report_excludes_prs_and_selects_top():
    issues = [gh_issue(1, "vague", body=""), gh_issue(2, "PR", pr=True),
              gh_issue(3, "Clear one", body=GOOD, labels=["good first issue"])]
    r = cli.build_report(args("--repo", "o/r"), session=gh_session(issues))
    assert r.fetched == 2 and r.excluded_pull_requests == 1
    assert r.selected.issue.id == "3"
    text = render_text(r, top=5)
    assert "#3" in text and "Investigation plan for #3" in text and "excluded 1 pull request" in text


def test_issue_url_selects_issue_mode():
    session = FakeSession(routes={"/repos/o/r": FakeResponse(200, REPO_META),
                                  "/repos/o/r/issues/3": FakeResponse(200, gh_issue(3, body=GOOD))})
    r = cli.build_report(args("--repo", "https://github.com/o/r/issues/3"), session=session)
    assert r.selected.issue.id == "3" and r.ranked == []


def test_issue_that_is_pr_is_rejected(capsys):
    session = FakeSession(routes={"/repos/o/r": FakeResponse(200, REPO_META),
                                  "/repos/o/r/issues/5": FakeResponse(200, gh_issue(5, pr=True))})
    with pytest.raises(Exception, match="pull request"):
        cli.build_report(args("--repo", "o/r", "--issue", "5"), session=session)


@pytest.mark.parametrize("bad", ["abc", "0", "-3", "1.5"])
def test_bad_issue_number(bad):
    with pytest.raises(Exception, match="positive issue number"):
        cli.build_report(args("--repo", "o/r", "--issue", bad), session=gh_session([]))


def test_closed_issue_warns():
    session = FakeSession(routes={"/repos/o/r": FakeResponse(200, REPO_META),
                                  "/repos/o/r/issues/3": FakeResponse(200, gh_issue(3, state="closed"))})
    r = cli.build_report(args("--repo", "o/r", "--issue", "#3"), session=session)
    assert any("closed" in w for w in r.warnings)


def test_empty_results_with_label_hint():
    r = cli.build_report(args("--repo", "o/r", "--label", "good first issue"), session=gh_session([]))
    assert r.ranked == [] and r.selected is None
    assert any("good first issue" in w and "try without --label" in w for w in r.warnings)
    assert "No candidate issues found" in render_text(r, top=5)


def test_archived_repo_warns_and_disabled_issues_fail():
    meta = dict(REPO_META, archived=True)
    r = cli.build_report(args("--repo", "o/r"), session=gh_session([gh_issue(1)], meta))
    assert any("archived" in w for w in r.warnings)
    with pytest.raises(Exception, match="disabled"):
        cli.build_report(args("--repo", "o/r"), session=gh_session([], dict(REPO_META, has_issues=False)))


def test_json_output_is_valid_and_has_disclaimer():
    r = cli.build_report(args("--repo", "o/r"), session=gh_session([gh_issue(1, body=GOOD)]))
    data = json.loads(render_json(r, top=5))
    assert data["ranked"][0]["issue"]["id"] == "1"
    assert "heuristic" in data["disclaimer"]


def test_ai_failure_falls_back_to_deterministic():
    def failing_runner(**_):
        raise AIUnavailableError("no GOOGLE_API_KEY set")

    r = cli.build_report(args("--repo", "o/r", "--ai"), session=gh_session([gh_issue(1, body=GOOD)]),
                         ai_runner=failing_runner)
    assert r.ai is None and r.ranked
    assert any("AI analysis unavailable" in w for w in r.warnings)


def test_ai_result_is_attached():
    def ok_runner(report, ctx, model):
        assert model == "gemini-flash-latest" and "github" in ctx
        return AIResult(text="Summary: fine", model=model)

    r = cli.build_report(args("--repo", "o/r", "--ai"), session=gh_session([gh_issue(1, body=GOOD)]), ai_runner=ok_runner)
    assert "AI analysis (gemini-flash-latest)" in render_text(r, top=5)


def test_ai_on_tracker_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "tok_value")
    issue = {"id": "1", "shortId": "W-1", "title": "KeyError: 'id'", "culprit": "api/views.py", "count": "3",
             "userCount": 1, "level": "error", "metadata": {"type": "KeyError", "value": "'id' missing in payload"}}
    session = FakeSession([FakeResponse(200, [issue]), FakeResponse(200, {"entries": []})])

    def never(**_):
        raise AssertionError("AI must not run without opt-in")

    r = cli.build_report(args("--source", "sentry", "--org", "acme", "--project", "web", "--ai"),
                         session=session, ai_runner=never)
    assert any("--allow-private-data-to-ai" in w for w in r.warnings)
    assert r.selected.issue.display_id == "W-1"


def test_tracker_event_failure_is_a_warning(monkeypatch):
    monkeypatch.setenv("GLITCHTIP_AUTH_TOKEN", "tok_value")
    issue = {"id": "1", "shortId": "W-1", "title": "Boom", "count": "3", "userCount": 1}
    session = FakeSession([FakeResponse(200, [issue]), FakeResponse(404, {})])
    r = cli.build_report(args("--source", "glitchtip", "--base-url", "https://gt.example.com",
                              "--org", "acme", "--project", "web"), session=session)
    assert r.selected and any("latest event" in w for w in r.warnings)


@pytest.mark.parametrize("argv, msg", [
    (["--source", "sentry", "--org", "a", "--project", "b", "--label", "x"], "--label only applies"),
    (["--source", "sentry", "--repo", "o/r"], "--repo is for --source github"),
    (["--repo", "o/r", "--org", "acme"], "are for --source sentry"),
    (["--source", "sentry", "--org", "a", "--project", "b"], "SENTRY_AUTH_TOKEN"),
])
def test_source_option_conflicts(argv, msg, capsys):
    assert cli.main(argv) == 2
    assert msg in capsys.readouterr().err


def test_main_reports_rate_limit_as_json(monkeypatch, capsys):
    def boom(_args):
        raise RateLimitError("GitHub rate limit reached.")

    monkeypatch.setattr(cli, "build_report", boom)
    assert cli.main(["--repo", "o/r", "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "GitHub rate limit reached."}


def test_unexpected_error_is_redacted(monkeypatch, capsys):
    def boom(_args):
        raise RuntimeError("leaked ghp_" + "x" * 36)

    monkeypatch.setattr(cli, "build_report", boom)
    assert cli.main(["--repo", "o/r"]) == 1
    err = capsys.readouterr().err
    assert "ghp_" not in err and "Unexpected error" in err


def test_terminal_control_sequences_are_stripped():
    evil = gh_issue(1, title="Nice title\x1b[2J\x1b]0;pwned\x07\rFAKE", body=GOOD)
    r = cli.build_report(args("--repo", "o/r"), session=gh_session([evil]))
    out = render_text(r, top=5)
    assert "\x1b" not in out and "\x07" not in out and "\r" not in out


def test_env_example_placeholders_count_as_unset(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "your_github_token_here")
    assert cli._env("GITHUB_TOKEN") is None
    monkeypatch.setenv("GOOGLE_API_KEY", "your_gemini_api_key_here")
    from good_first_issue_agent.agent import _has_credentials
    assert _has_credentials() is False

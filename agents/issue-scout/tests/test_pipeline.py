import json

import pytest

from conftest import NOW, FakeClient, comment, cross_ref, issue_payload, pull, repo_payload
from issue_scout import cli, tools
from issue_scout.github import GitHubError, RateLimitError, parse_issue_url
from issue_scout.models import Profile
from issue_scout.report import render_find
from issue_scout.scout import Scout


def world(rate_limit_timeline_for=None):
    """Two repos, four issues: one clean, one with an open PR, one claimed, one fixed per maintainer."""
    repos = [repo_payload("acme/app"), repo_payload("acme/lib", stars=400)]
    issues = [
        issue_payload(1, "acme/app", title="Crash in config parser"),
        issue_payload(2, "acme/app", title="Add retry option"),
        issue_payload(3, "acme/lib", title="Typo in docs", labels=("documentation", "good first issue")),
        issue_payload(4, "acme/lib", title="Wrong default timeout"),
    ]
    timelines = {
        ("acme/app", 1): [comment("Thanks, confirmed", role="MEMBER")],
        ("acme/app", 2): [cross_ref(20, state="open", repo="acme/app")],
        ("acme/lib", 3): [comment("Can I work on this?", author="eager", days_ago=2)],
        ("acme/lib", 4): [comment("Fixed in #50", author="maint", role="OWNER")],
    }
    routes = {
        "/search/repositories": {"items": repos},
        "/search/issues": {"items": issues},
        "/repos/acme/app/pulls": [pull(merged_days=2), pull(merged_days=3), pull(merged_days=1), pull()],
        "/repos/acme/lib/pulls": [pull(merged_days=5), pull(merged_days=8), pull(merged_days=6)],
    }
    for (repo, number), events in timelines.items():
        path = "/repos/%s/issues/%d/timeline" % (repo, number)
        routes[path] = RateLimitError("GitHub rate limit reached.", 403) if (repo, number) == rate_limit_timeline_for else events
    return FakeClient(routes)


def test_find_ranks_and_filters_dead_ends():
    client = world()
    result = Scout(client, now=NOW).find(Profile(languages=["python"], hours=3), limit=5)

    assert [c.ref for c in result.candidates] == ["acme/app#1", "acme/lib#3"]
    assert result.candidates[0].verdict == "ready"
    assert result.candidates[1].verdict == "caution" and "recently-claimed" in result.candidates[1].flags
    assert sorted(c.ref for c in result.skipped) == ["acme/app#2", "acme/lib#4"]
    assert result.skip_summary() == {"open-pr": 1, "likely-resolved": 1}

    repo_query = next(p["q"] for path, p in client.calls if path == "/search/repositories")
    issue_query = next(p["q"] for path, p in client.calls if path == "/search/issues")
    assert 'language:"python"' in repo_query and "good-first-issues:>=2" in repo_query
    assert "-linked:pr" in issue_query and "no:assignee" in issue_query
    assert 'label:"good first issue","help wanted"' in issue_query
    assert "repo:acme/app" in issue_query and "repo:acme/lib" in issue_query

    text = render_find(result, NOW)
    assert "Filtered out 2 dead ends" in text
    assert "acme/app#1" in text and "acme/app#2" not in text


def test_find_survives_rate_limit_with_partial_results():
    client = world(rate_limit_timeline_for=("acme/lib", 3))
    result = Scout(client, now=NOW).find(Profile(languages=["python"]), limit=5)
    assert "acme/lib#3" not in [c.ref for c in result.candidates + result.skipped]
    assert any("rate limit" in note for note in result.notes)


def test_find_keeps_issues_found_before_search_rate_limit():
    client = world()
    client.routes["/search/repositories"] = {"items": [repo_payload("acme/app")] + [repo_payload("x/r%d" % i) for i in range(10)]}
    calls = {"n": 0}

    def issues(params):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RateLimitError("GitHub rate limit reached.", 403)
        return {"items": [issue_payload(1, "acme/app", title="Crash in config parser")]}

    client.routes["/search/issues"] = issues
    result = Scout(client, now=NOW).find(Profile(languages=["python"]), limit=5)
    assert [c.ref for c in result.candidates] == ["acme/app#1"]
    assert any("Searched 6 of 11 repos" in note for note in result.notes)


def test_prescore_prefers_just_updated_issues():
    scout = Scout(FakeClient({}), now=NOW)
    fresh = issue_payload(1, updated=0)
    stale = issue_payload(2, updated=200)
    assert scout._prescore(fresh) > scout._prescore(stale)


def test_find_caps_candidates_without_token():
    client = world()
    client.routes["/search/issues"] = {"items": [issue_payload(n, "acme/app") for n in range(100, 140)]}
    for n in range(100, 140):
        client.routes["/repos/acme/app/issues/%d/timeline" % n] = []
    result = Scout(client, now=NOW).find(Profile(languages=["python"]), limit=3)
    timeline_calls = [path for path, _ in client.calls if path.endswith("/timeline")]
    assert len(timeline_calls) <= 2  # MAX_PER_REPO keeps one repo from crowding the list
    assert any("GITHUB_TOKEN" in note for note in result.notes)


def test_inspect_closed_issue_is_skip():
    client = world()
    client.routes["/repos/acme/app/issues/1"] = issue_payload(1, "acme/app", state="closed")
    client.routes["/repos/acme/app"] = repo_payload("acme/app")
    candidate = Scout(client, now=NOW).inspect("https://github.com/acme/app/issues/1")
    assert candidate.verdict == "skip" and candidate.flags[0] == "closed"


def test_inspect_rejects_pull_requests():
    client = world()
    client.routes["/repos/acme/app/issues/1"] = dict(issue_payload(1, "acme/app"), pull_request={})
    with pytest.raises(ValueError):
        Scout(client, now=NOW).inspect("acme/app#1")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://github.com/o/r/issues/12", ("o/r", 12)),
        ("o/r#12", ("o/r", 12)),
        ("o/r/issues/12", ("o/r", 12)),
        ("github.com/o/r/issues/12?x=1", ("o/r", 12)),
    ],
)
def test_parse_issue_url(value, expected):
    assert parse_issue_url(value) == expected


def test_parse_issue_url_rejects_garbage():
    with pytest.raises(ValueError):
        parse_issue_url("not an issue")


def test_profile_from_user_infers_languages(now):
    client = FakeClient(
        {
            "/users/dev/repos": [
                {"language": "Python", "pushed_at": "2026-10-01T00:00:00Z", "topics": ["ml", "cli"]},
                {"language": "Python", "pushed_at": "2026-09-01T00:00:00Z", "topics": ["ml"]},
                {"language": "Go", "pushed_at": "2026-08-01T00:00:00Z", "topics": []},
                {"language": "Rust", "pushed_at": "2026-08-01T00:00:00Z", "fork": True},
                {"language": "Java", "pushed_at": "2019-01-01T00:00:00Z"},
            ]
        }
    )
    profile = Scout(client, now=now).profile_from_user("dev", hours=2)
    assert profile.languages == ["python", "go"]
    assert profile.topics == ["ml"]
    assert profile.hours == 2


def test_cli_requires_lang_or_user(capsys):
    assert cli.main(["find"]) == 2
    assert "--lang" in capsys.readouterr().err


def test_cli_find_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Scout", lambda: Scout(world(), now=NOW))
    assert cli.main(["find", "--lang", "python,go", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["profile"]["languages"] == ["python", "go"]
    assert [c["ref"] for c in data["candidates"]] == ["acme/app#1", "acme/lib#3"]


def test_cli_reports_github_errors(monkeypatch, capsys):
    class Broken(Scout):
        def inspect(self, ref, profile=None):
            raise GitHubError("GitHub API error 404: Not Found", 404)

    monkeypatch.setattr(cli, "Scout", lambda: Broken(FakeClient({})))
    assert cli.main(["inspect", "o/r#1"]) == 1
    assert "404" in capsys.readouterr().err


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nGITHUB_TOKEN=from_file\nISSUE_SCOUT_MODEL='m'\nEMPTY=\n")
    monkeypatch.setenv("GITHUB_TOKEN", "from_env")
    monkeypatch.delenv("ISSUE_SCOUT_MODEL", raising=False)
    cli.load_dotenv(env)
    import os

    assert os.environ["GITHUB_TOKEN"] == "from_env"
    assert os.environ["ISSUE_SCOUT_MODEL"] == "m"
    monkeypatch.delenv("ISSUE_SCOUT_MODEL")


def test_tools_return_errors_instead_of_raising(monkeypatch):
    monkeypatch.setattr(tools, "_scout", lambda: Scout(FakeClient({}), now=NOW))
    assert "error" in tools.inspect_issue("o/r#1")
    assert "error" in tools.inspect_issue("garbage")
    assert "error" in tools.related_issues("o/r#1")


def test_tools_find_issues_is_json_serialisable(monkeypatch):
    monkeypatch.setattr(tools, "_scout", lambda: Scout(world(), now=NOW))
    data = tools.find_issues(languages=["python"], limit=2)
    json.dumps(data)
    assert "skipped" not in data and data["skip_summary"] == {"open-pr": 1, "likely-resolved": 1}


def test_brief_facts_degrade_when_extras_fail():
    client = world()
    client.routes["/repos/acme/app/issues/1"] = client.routes["/search/issues"]["items"][0]
    client.routes["/repos/acme/app"] = repo_payload("acme/app")
    client.routes["/search/issues"] = RateLimitError("GitHub's abuse protection paused requests.", 403)
    # community profile and git tree routes are missing too -> 404s
    facts = Scout(client, now=NOW).brief_facts("acme/app#1")
    assert facts["issue"]["ref"] == "acme/app#1" and facts["issue"]["verdict"] == "ready"
    assert facts["related"] == {"open_issues": [], "closed_issues": [], "merged_prs": []}
    assert any("Related issues unavailable" in note for note in facts["notes"])
    assert any("File suggestions unavailable" in note for note in facts["notes"])
    from issue_scout.report import render_brief

    assert "Related issues unavailable" in render_brief(facts, NOW)

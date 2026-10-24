import base64

import pytest
import requests
from conftest import FakeResponse, FakeSession, gh_issue

from good_first_issue_agent.errors import (
    AuthError,
    InvalidInputError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from good_first_issue_agent.github_client import GitHubClient, RepoRef, parse_repo


# --- parse_repo ---------------------------------------------------------------
@pytest.mark.parametrize("value, expected", [
    ("pallets/flask", ("pallets", "flask", None)),
    ("  pallets/flask  ", ("pallets", "flask", None)),
    ("https://github.com/pallets/flask", ("pallets", "flask", None)),
    ("https://github.com/pallets/flask/", ("pallets", "flask", None)),
    ("https://github.com/pallets/flask.git", ("pallets", "flask", None)),
    ("github.com/pallets/flask", ("pallets", "flask", None)),
    ("https://www.github.com/pallets/flask/tree/main/src", ("pallets", "flask", None)),
    ("https://github.com/pallets/flask/issues/5123", ("pallets", "flask", 5123)),
    ("pallets/flask/issues/7", ("pallets", "flask", 7)),
    ("git@github.com:pallets/flask.git", ("pallets", "flask", None)),
    ("my-org/repo.name_1", ("my-org", "repo.name_1", None)),
])
def test_parse_repo_accepts_common_forms(value, expected):
    ref = parse_repo(value)
    assert (ref.owner, ref.repo, ref.issue) == expected


@pytest.mark.parametrize("value", [
    "", "   ", "flask", "https://gitlab.com/a/b", "https://github.com/onlyowner",
    "-bad/repo", "owner/..", "owner/repo/extra", "own er/repo", "owner/re po",
])
def test_parse_repo_rejects_malformed(value):
    with pytest.raises(InvalidInputError):
        parse_repo(value)


# --- list_issues --------------------------------------------------------------
def _client(session, token=None, **kw):
    return GitHubClient(RepoRef("o", "r"), token=token, session=session, **kw)


def test_pull_requests_are_excluded_and_counted():
    page = [gh_issue(1), gh_issue(2, pr=True), gh_issue(3), gh_issue(4, pr=True)]
    session = FakeSession([FakeResponse(200, page)])
    issues, excluded = _client(session).list_issues(limit=10)
    assert [i.id for i in issues] == ["1", "3"]
    assert excluded == 2
    assert all(i.source == "github" for i in issues)


def test_limit_stops_early():
    page = [gh_issue(n) for n in range(1, 31)]
    session = FakeSession([FakeResponse(200, page, links={"next": {"url": "n"}})])
    issues, _ = _client(session).list_issues(limit=5)
    assert len(issues) == 5
    assert len(session.calls) == 1


def test_pagination_is_bounded():
    def full_page(start):
        return FakeResponse(200, [gh_issue(n, pr=True) for n in range(start, start + 30)], links={"next": {"url": "n"}})

    session = FakeSession([full_page(i * 100) for i in range(10)])
    issues, excluded = _client(session).list_issues(limit=5)
    assert issues == []
    assert len(session.calls) == 3  # MAX_PAGES, never the whole history
    assert excluded == 90


def test_labels_and_query_params():
    session = FakeSession([FakeResponse(200, [])])
    _client(session).list_issues(labels=["good first issue", "docs"], limit=10)
    params = session.calls[0]["params"]
    assert params["labels"] == "good first issue,docs"
    assert params["state"] == "open"
    assert session.calls[0]["timeout"] == 10.0


def test_missing_body_and_labels_are_normalized():
    raw = gh_issue(9, body=None)
    raw["labels"] = [{"name": "bug"}, "plain-string-label"]
    session = FakeSession([FakeResponse(200, [raw])])
    issues, _ = _client(session).list_issues()
    assert issues[0].body == ""
    assert issues[0].labels == ["bug", "plain-string-label"]


def test_token_sent_only_when_configured():
    s1 = FakeSession([FakeResponse(200, [])])
    _client(s1).list_issues()
    assert "Authorization" not in s1.calls[0]["headers"]

    s2 = FakeSession([FakeResponse(200, [])])
    _client(s2, token="ghp_secretvalue1234567890").list_issues()
    assert s2.calls[0]["headers"]["Authorization"] == "Bearer ghp_secretvalue1234567890"


# --- errors -----------------------------------------------------------------------
def test_repo_not_found():
    session = FakeSession([FakeResponse(404, {"message": "Not Found"})])
    with pytest.raises(NotFoundError, match="o/r was not found"):
        _client(session).get_repo()


def test_rate_limit_message_includes_reset_and_token_hint():
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1792827657"}
    session = FakeSession([FakeResponse(403, {"message": "rate limit"}, headers=headers)])
    with pytest.raises(RateLimitError) as exc:
        _client(session).list_issues()
    assert "resets at" in str(exc.value)
    assert "GITHUB_TOKEN" in str(exc.value)


def test_secondary_rate_limit_429():
    session = FakeSession([FakeResponse(429, {}, headers={"Retry-After": "30"})])
    with pytest.raises(RateLimitError, match="30 seconds"):
        _client(session).list_issues()


def test_bad_token_is_never_echoed():
    token = "ghp_thisIsASecretToken1234567890"
    session = FakeSession([FakeResponse(401, {"message": "Bad credentials"})])
    with pytest.raises(AuthError) as exc:
        _client(session, token=token).get_repo()
    assert token not in str(exc.value)


def test_forbidden_without_rate_limit_is_auth_error():
    session = FakeSession([FakeResponse(403, {}, headers={"X-RateLimit-Remaining": "40"})])
    with pytest.raises(AuthError):
        _client(session).get_repo()


def test_server_error_is_retried_once_then_succeeds():
    session = FakeSession([FakeResponse(502, {}), FakeResponse(200, [gh_issue(1)])])
    issues, _ = _client(session).list_issues()
    assert len(issues) == 1 and len(session.calls) == 2


def test_server_error_twice_raises():
    session = FakeSession([FakeResponse(500, {}), FakeResponse(503, {})])
    with pytest.raises(UpstreamError, match="server error"):
        _client(session).list_issues()


def test_timeout_is_retried_then_reported():
    session = FakeSession([requests.Timeout(), requests.Timeout()])
    with pytest.raises(UpstreamError, match="did not respond"):
        _client(session).get_repo()
    assert len(session.calls) == 2


def test_connection_error():
    session = FakeSession([requests.ConnectionError(), requests.ConnectionError()])
    with pytest.raises(UpstreamError, match="Could not connect"):
        _client(session).get_repo()


def test_tls_interception_gets_specific_message():
    session = FakeSession([requests.exceptions.SSLError("self-signed certificate")])
    with pytest.raises(UpstreamError, match="REQUESTS_CA_BUNDLE"):
        _client(session).get_repo()


def test_invalid_json():
    session = FakeSession([FakeResponse(200, text="<html>")])
    with pytest.raises(UpstreamError, match="not valid JSON"):
        _client(session).get_repo()


def test_issues_disabled_410():
    session = FakeSession([FakeResponse(410, {})])
    with pytest.raises(NotFoundError, match="disabled"):
        _client(session).list_issues()


# --- single issue / files -----------------------------------------------------------
def test_get_issue_rejects_pull_request():
    session = FakeSession([FakeResponse(200, gh_issue(5, pr=True))])
    with pytest.raises(InvalidInputError, match="pull request"):
        _client(session).get_issue(5)


def test_get_issue_not_found():
    session = FakeSession([FakeResponse(404, {})])
    with pytest.raises(NotFoundError, match="#77"):
        _client(session).get_issue(77)


def test_read_file_decodes_and_truncates():
    content = base64.b64encode(("x" * 50).encode()).decode()
    session = FakeSession([FakeResponse(200, {"type": "file", "encoding": "base64", "content": content})])
    text = _client(session).read_file("README.md", max_chars=10)
    assert text.startswith("x" * 10) and "truncated" in text


def test_read_file_refuses_binary():
    content = base64.b64encode(b"\x89PNG\x00\x00").decode()
    session = FakeSession([FakeResponse(200, {"type": "file", "encoding": "base64", "content": content})])
    with pytest.raises(InvalidInputError, match="binary"):
        _client(session).read_file("logo.png")


def test_read_file_refuses_directory():
    session = FakeSession([FakeResponse(200, [{"name": "a", "path": "a", "type": "file"}])])
    with pytest.raises(InvalidInputError, match="not a file"):
        _client(session).read_file("src")


@pytest.mark.parametrize("value", ["gitlab.com/foo/bar", "bitbucket.org/a/b"])
def test_other_hosts_get_clear_message(value):
    with pytest.raises(InvalidInputError, match="Only github.com"):
        parse_repo(value)

"""GitHubClient error handling, retries and pacing, with urlopen replaced by a stub."""

import io
import json
import urllib.error
from email.message import Message

import pytest

from issue_scout import github
from issue_scout.github import GitHubClient, RateLimitError, SecondaryRateLimitError


def http_error(code, message, **headers):
    msg = Message()
    for key, value in headers.items():
        msg[key.replace("_", "-")] = value
    body = io.BytesIO(json.dumps({"message": message}).encode())
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", msg, body)


class Ok:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.data).encode()


def stub_urlopen(monkeypatch, responses):
    calls = []

    def fake(request, timeout=None):
        calls.append(request)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return Ok(item)

    monkeypatch.setattr(github.urllib.request, "urlopen", fake)
    return calls


def test_secondary_limit_is_retried_with_backoff(monkeypatch):
    calls = stub_urlopen(
        monkeypatch,
        [http_error(403, "You have exceeded a secondary rate limit."), {"items": [{"number": 1}]}],
    )
    waits = []
    client = GitHubClient(token="t", sleep=waits.append)
    assert client.search_issues("q") == [{"number": 1}]
    assert len(calls) == 2
    assert github.SECONDARY_BACKOFF[0] in waits


def test_secondary_limit_honours_retry_after(monkeypatch):
    stub_urlopen(monkeypatch, [http_error(429, "secondary rate limit", Retry_After="20"), {"ok": True}])
    waits = []
    GitHubClient(token="t", sleep=waits.append).get("/repos/o/r")
    assert waits == [20.0]


def test_secondary_limit_gives_up_with_clear_message(monkeypatch):
    errors = [http_error(403, "You have exceeded a secondary rate limit.") for _ in range(3)]
    stub_urlopen(monkeypatch, errors)
    with pytest.raises(SecondaryRateLimitError) as info:
        GitHubClient(token="t", sleep=lambda s: None).get("/repos/o/r")
    assert "abuse protection" in str(info.value)
    assert "GITHUB_TOKEN" not in str(info.value)


def test_primary_limit_advice_depends_on_token(monkeypatch):
    stub_urlopen(monkeypatch, [http_error(403, "API rate limit exceeded", X_RateLimit_Remaining="0")] * 2)
    with pytest.raises(RateLimitError) as anonymous:
        GitHubClient(token="", sleep=lambda s: None).get("/a")
    with pytest.raises(RateLimitError) as authed:
        GitHubClient(token="t", sleep=lambda s: None).get("/b")
    assert "Set GITHUB_TOKEN" in str(anonymous.value)
    assert "Set GITHUB_TOKEN" not in str(authed.value)
    assert not isinstance(authed.value, SecondaryRateLimitError)


def test_searches_are_paced_but_other_calls_are_not(monkeypatch):
    stub_urlopen(monkeypatch, [{"items": []}, {"items": []}, {"x": 1}])
    waits = []
    client = GitHubClient(token="t", sleep=waits.append)
    client.search_issues("a")
    client.search_issues("b")
    client.get("/repos/o/r")
    assert len(waits) == 1 and 0 < waits[0] <= github.SEARCH_INTERVAL


def test_token_is_sent_and_responses_are_cached(monkeypatch):
    calls = stub_urlopen(monkeypatch, [{"x": 1}])
    client = GitHubClient(token="secret", sleep=lambda s: None)
    assert client.get("/repos/o/r") == client.get("/repos/o/r") == {"x": 1}
    assert len(calls) == 1
    assert calls[0].get_header("Authorization") == "Bearer secret"

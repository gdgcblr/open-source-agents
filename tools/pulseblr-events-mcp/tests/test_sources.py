import asyncio
import copy
import json
import logging
from datetime import datetime

import pytest

from pulseblr_events_mcp import sources
from pulseblr_events_mcp.errors import InputError, SourceError

EVENT = {
    "id": "0123456789abcdef01234567",
    "title": "Public engineering meetup",
    "url": "https://pulseblr-u9f1.vercel.app/events/0123456789abcdef01234567",
    "startsAt": "2026-10-24T10:00:00+05:30",
    "endsAt": "2026-10-24T11:00:00+05:30",
    "format": "offline",
    "organizer": "Example community",
    "categories": ["AI/ML"],
    "connectionScore": 70,
    "isFree": True,
    "source": "example",
    "sourceUrl": "https://example.com/meetup",
}


def run(awaitable):
    return asyncio.run(awaitable)


def mock_upstream(monkeypatch, *, result=None, status=200, redirect=None, raw=None):
    requests = []
    transport_options = []

    async def handler(request):
        requests.append(request)
        assert str(request.url) == sources.PUBLIC_ENDPOINT
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        if status != 200:
            return sources.httpx2.Response(status, headers={"location": redirect or "/elsewhere"})
        if request.method == "DELETE":
            return sources.httpx2.Response(204)
        payload = json.loads(request.content)
        if "id" not in payload:
            return sources.httpx2.Response(202)
        method = payload["method"]
        if method == "initialize":
            data = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock-public", "version": "1"},
            }
        elif method == "tools/list":
            data = {
                "tools": [
                    {
                        "name": "search_events",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "array",
                                    "items": {"enum": ["AI/ML", "Open Source"]},
                                },
                                "area": {
                                    "type": "array",
                                    "items": {"enum": ["Indiranagar", "Whitefield"]},
                                },
                            },
                        },
                    },
                    {
                        "name": "trending_topics",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "limit": {"type": "integer", "maximum": 22},
                            },
                        },
                    },
                ]
            }
        else:
            name = payload["params"]["name"]
            assert name in {"search_events", "get_event", "trending_topics"}
            if callable(result):
                data = result(name, payload["params"].get("arguments", {}))
            elif result is not None:
                data = result
            else:
                data = {
                    "structuredContent": {"events": [copy.deepcopy(EVENT)], "totalMatching": 2},
                    "content": [],
                }
        if raw is not None and method == "tools/call":
            return sources.httpx2.Response(
                200, headers={"content-type": "application/json"}, content=raw
            )
        return sources.httpx2.Response(
            200, json={"jsonrpc": "2.0", "id": payload["id"], "result": data}
        )

    def transport(**kwargs):
        transport_options.append(kwargs)
        return sources.httpx2.MockTransport(handler)

    monkeypatch.setattr(sources.httpx2, "AsyncHTTPTransport", transport)
    return requests, transport_options


def test_sample_is_packaged_offline_cwd_independent_and_explicitly_fictional(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sources.httpx2, "AsyncHTTPTransport", lambda **_: pytest.fail("sample used network")
    )
    result = run(sources.SampleSource().search({"limit": 50}))
    assert len(result["events"]) >= 10
    assert result["data_mode"] == "sample"
    assert any("fictional" in warning.lower() for warning in result["warnings"])
    assert all(event["url"].startswith("https://example.com/") for event in result["events"])
    assert all(
        event["startsAt"].startswith(("2026-10-24", "2026-10-25")) for event in result["events"]
    )


def test_sample_filters_count_before_limit_and_returns_fresh_copies():
    source = sources.SampleSource()
    result = run(
        source.search({"category": ["AI/ML"], "format": "offline", "free": True, "limit": 1})
    )
    assert len(result["events"]) == 1
    assert result["total_matching"] > 1
    assert result["candidate_pool_truncated"] is True
    event = result["events"][0]
    assert event["format"] == "offline" and event["isFree"] is True
    assert "AI/ML" in event["categories"]
    event["title"] = "Changed by caller"
    assert run(source.get_event(event["id"]))["title"] != "Changed by caller"
    assert run(source.get_event("missing-sample-id")) is None


def test_sample_date_to_is_inclusive_date_but_timestamp_is_exact():
    source = sources.SampleSource()
    result = run(source.search({"dateFrom": "2026-10-25", "dateTo": "2026-10-25", "limit": 50}))
    assert result["events"]
    assert all(event["startsAt"].startswith("2026-10-25") for event in result["events"])
    assert run(source.search({"dateFrom": "2026-10-26", "limit": 50}))["events"] == []


def test_live_uses_official_protocol_bounded_candidates_and_no_env_transport(monkeypatch):
    requests, options = mock_upstream(monkeypatch)
    result = run(sources.LiveSource().search({"limit": 1, "category": ["AI/ML"]}))
    assert result["data_mode"] == "live"
    assert result["total_matching"] == 2
    assert result["candidate_pool_truncated"] is True
    assert result["fetched_at"].endswith("Z")
    methods = [
        json.loads(request.content)["method"] for request in requests if request.method == "POST"
    ]
    assert methods[:3] == ["initialize", "notifications/initialized", "tools/call"]
    assert set(methods) <= {"initialize", "notifications/initialized", "tools/call", "tools/list"}
    tool_call = next(
        request
        for request in requests
        if request.method == "POST" and json.loads(request.content)["method"] == "tools/call"
    )
    args = json.loads(tool_call.content)["params"]["arguments"]
    assert args["limit"] == 1
    assert options[0]["trust_env"] is False
    assert any("free" in item.lower() for item in result["warnings"])


def test_live_allowlists_event_fields_and_deduplicates_ids(monkeypatch):
    event = dict(EVENT, internalToken="DO_NOT_RETURN", privateEmail="private@example.com")
    mock_upstream(
        monkeypatch,
        result={"content": [], "structuredContent": {"events": [event, event], "totalMatching": 2}},
    )
    result = run(sources.LiveSource().search({"limit": 50}))
    assert len(result["events"]) == 1
    assert "DO_NOT_RETURN" not in json.dumps(result)
    assert "privateEmail" not in json.dumps(result)


@pytest.mark.parametrize(
    "filters",
    [
        {"limit": 51},
        {"limit": True},
        {"url": "https://private.example"},
        {"free": "yes"},
        {"format": []},
        {"sort": {}},
    ],
)
def test_invalid_search_arguments_never_reach_transport(monkeypatch, filters):
    monkeypatch.setattr(
        sources.httpx2, "AsyncHTTPTransport", lambda **_: pytest.fail("invalid input used network")
    )
    with pytest.raises(InputError):
        run(sources.LiveSource().search(filters))


@pytest.mark.parametrize("event_id", ["https://example.com/private", "../secret", "", "x" * 300])
def test_live_rejects_caller_urls_and_bad_ids_before_network(monkeypatch, event_id):
    monkeypatch.setattr(
        sources.httpx2, "AsyncHTTPTransport", lambda **_: pytest.fail("invalid ID used network")
    )
    with pytest.raises(InputError):
        run(sources.LiveSource().get_event(event_id))


@pytest.mark.parametrize("status", [302, 307, 429, 500])
def test_http_failures_are_safe_and_never_fall_back_to_sample(monkeypatch, status):
    requests, _ = mock_upstream(
        monkeypatch, status=status, redirect="https://private.example/DO_NOT_RETURN"
    )
    with pytest.raises(SourceError) as failure:
        run(sources.LiveSource().search({"limit": 1}))
    assert "DO_NOT_RETURN" not in str(failure.value)
    assert "sample" in str(failure.value).lower()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "result",
    [
        {"content": [{"type": "text", "text": "DO_NOT_RETURN"}], "isError": True},
        {"content": [], "structuredContent": {"events": "DO_NOT_RETURN"}},
        {"content": [], "structuredContent": {"events": [], "totalMatching": -1}},
    ],
)
def test_mcp_errors_and_malformed_payloads_are_redacted(monkeypatch, result):
    mock_upstream(monkeypatch, result=result)
    with pytest.raises(SourceError) as failure:
        run(sources.LiveSource().search({"limit": 1}))
    assert "DO_NOT_RETURN" not in str(failure.value)


def test_oversized_and_invalid_json_responses_are_bounded(monkeypatch):
    mock_upstream(monkeypatch, raw=b"X" * (sources.MAX_RESPONSE_BYTES + 1))
    with pytest.raises(SourceError):
        run(sources.LiveSource().search({"limit": 1}))
    mock_upstream(monkeypatch, raw=b"not json DO_NOT_RETURN")
    with pytest.raises(SourceError) as failure:
        run(sources.LiveSource().search({"limit": 1}))
    assert "DO_NOT_RETURN" not in str(failure.value)


def test_live_timeout_has_no_raw_exception_details(monkeypatch):
    async def handler(_):
        raise sources.httpx2.ReadTimeout("private.example DO_NOT_RETURN")

    monkeypatch.setattr(
        sources.httpx2, "AsyncHTTPTransport", lambda **_: sources.httpx2.MockTransport(handler)
    )
    with pytest.raises(SourceError) as failure:
        run(sources.LiveSource().search({"limit": 1}))
    assert "DO_NOT_RETURN" not in str(failure.value)


def test_topics_separate_supported_vocabulary_and_observed_counts(monkeypatch):
    def result(name, args):
        assert name == "trending_topics"
        assert args == {"limit": 22, "when": "weekend"}
        return {
            "content": [],
            "structuredContent": {
                "window": "weekend",
                "totalEvents": 3,
                "topics": [
                    {
                        "category": "Science/Research",
                        "events": 2,
                        "shareOfUpcoming": 2 / 3,
                        "url": "https://pulseblr-u9f1.vercel.app/topics/science",
                    },
                ],
            },
        }

    requests, _ = mock_upstream(monkeypatch, result=result)
    value = run(sources.LiveSource().topics("weekend"))
    assert value["supported_topics"] == ["AI/ML", "Open Source"]
    assert value["supported_areas"] == ["Indiranagar", "Whitefield"]
    assert value["observed_topics"][0]["category"] == "Science/Research"
    assert value["total_events"] == 3
    assert value["counts_truncated"] is False
    assert any(
        json.loads(request.content)["method"] == "tools/list"
        for request in requests
        if request.method == "POST"
    )


def test_get_event_normalizes_and_handles_explicit_not_found(monkeypatch):
    mock_upstream(monkeypatch, result={"content": [], "structuredContent": {"event": EVENT}})
    assert run(sources.LiveSource().get_event(EVENT["id"]))["id"] == EVENT["id"]
    mock_upstream(monkeypatch, result={"content": [], "structuredContent": {"event": None}})
    assert run(sources.LiveSource().get_event(EVENT["id"])) is None


def test_get_event_understands_only_narrowly_identified_public_not_found(monkeypatch):
    message = f'No public PulseBLR event with id "{EVENT["id"]}". Event pages are pruned about a week after they finish.'
    mock_upstream(
        monkeypatch, result={"content": [{"type": "text", "text": message}], "isError": True}
    )
    assert run(sources.LiveSource().get_event(EVENT["id"])) is None
    mock_upstream(
        monkeypatch,
        result={
            "content": [{"type": "text", "text": "Private failure DO_NOT_RETURN"}],
            "isError": True,
        },
    )
    with pytest.raises(SourceError) as failure:
        run(sources.LiveSource().get_event(EVENT["id"]))
    assert "DO_NOT_RETURN" not in str(failure.value)


def test_topic_urls_cannot_forward_unexpected_query_secrets(monkeypatch):
    result = {
        "content": [],
        "structuredContent": {
            "window": "week",
            "totalEvents": 2,
            "topics": [
                {
                    "category": "AI/ML",
                    "events": 2,
                    "url": "https://pulseblr-u9f1.vercel.app/topics/ai-ml?token=DO_NOT_RETURN#private",
                },
            ],
        },
    }
    mock_upstream(monkeypatch, result=result)
    assert "DO_NOT_RETURN" not in json.dumps(run(sources.LiveSource().topics("week")))


def test_stream_body_limit_also_applies_without_content_length(monkeypatch):
    class OversizedStream(sources.httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield b"X" * (sources.MAX_RESPONSE_BYTES // 2)
            yield b"X" * (sources.MAX_RESPONSE_BYTES // 2 + 1)

    async def handler(request):
        return sources.httpx2.Response(
            200, headers={"content-type": "application/json"}, stream=OversizedStream()
        )

    monkeypatch.setattr(
        sources.httpx2, "AsyncHTTPTransport", lambda **_: sources.httpx2.MockTransport(handler)
    )
    with pytest.raises(SourceError):
        run(sources.LiveSource().search({"limit": 1}))


def test_official_client_carries_session_and_version_but_never_cookie(monkeypatch):
    seen = []

    async def handler(request):
        seen.append(request)
        assert "cookie" not in request.headers
        if request.method == "GET":
            return sources.httpx2.Response(405)
        if request.method == "DELETE":
            assert request.headers["mcp-session-id"] == "public-test-session"
            return sources.httpx2.Response(204)
        body = json.loads(request.content)
        headers = {
            "set-cookie": "unwanted=DO_NOT_FORWARD; Path=/",
            "mcp-session-id": "public-test-session",
        }
        if body["method"] == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock", "version": "1"},
            }
        else:
            assert request.headers["mcp-session-id"] == "public-test-session"
            assert request.headers["mcp-protocol-version"] == "2025-03-26"
            if "id" not in body:
                return sources.httpx2.Response(202, headers=headers)
            if body["method"] == "tools/list":
                result = {"tools": []}
            else:
                result = {"content": [], "structuredContent": {"events": [], "totalMatching": 0}}
        return sources.httpx2.Response(
            200, headers=headers, json={"jsonrpc": "2.0", "id": body["id"], "result": result}
        )

    monkeypatch.setattr(
        sources.httpx2, "AsyncHTTPTransport", lambda **_: sources.httpx2.MockTransport(handler)
    )
    assert run(sources.LiveSource().search({"limit": 1}))["events"] == []
    assert any(request.method == "DELETE" for request in seen)


def test_invalid_event_rows_are_explicitly_omitted(monkeypatch):
    invalid = dict(EVENT, startsAt="not-a-timestamp")
    mock_upstream(
        monkeypatch,
        result={
            "content": [],
            "structuredContent": {"events": [invalid, EVENT], "totalMatching": 2},
        },
    )
    result = run(sources.LiveSource().search({"limit": 50}))
    assert len(result["events"]) == 1
    assert result["candidate_pool_truncated"] is True
    assert any("Skipped 1" in warning for warning in result["warnings"])


def test_raw_upstream_parse_errors_do_not_leak_through_sdk_logging(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="mcp.client.streamable_http")
    mock_upstream(monkeypatch, raw=b"not json DO_NOT_RETURN")
    with pytest.raises(SourceError):
        run(sources.LiveSource().search({"limit": 1}))
    assert "DO_NOT_RETURN" not in caplog.text


def test_sample_topics_honor_explicit_clock_and_current_sunday_weekend():
    source = sources.SampleSource(now=datetime.fromisoformat("2026-10-25T08:00:00+05:30"))
    assert run(source.topics("today"))["total_events"] == 6
    assert run(source.topics("tomorrow"))["total_events"] == 0
    assert run(source.topics("weekend"))["total_events"] == 12

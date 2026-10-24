import asyncio
from datetime import datetime

import pytest

from pulseblr_events_mcp.errors import InputError, SourceError
from pulseblr_events_mcp.service import EventTools

NOW = datetime.fromisoformat("2026-10-24T08:00:00+05:30")


def event(event_id="sample-1", **changes):
    return {
        "id": event_id,
        "title": "AI meetup",
        "url": "https://example.com/e/1",
        "startsAt": "2026-10-24T09:00:00+05:30",
        "endsAt": "2026-10-24T10:00:00+05:30",
        "format": "offline",
        "organizer": "Example Builders",
        "categories": ["AI/ML"],
        "connectionScore": 50,
        "isFree": False,
        **changes,
    }


class FakeSource:
    data_mode = "sample"

    def __init__(self):
        self.search_calls = []
        self.get_calls = []

    async def search(self, filters):
        self.search_calls.append(filters)
        return {
            "events": [event()],
            "total_matching": 100,
            "candidate_pool_truncated": True,
            "data_mode": "sample",
            "fetched_at": NOW.isoformat(),
            "warnings": ["Fictional sample data."],
        }

    async def get_event(self, event_id):
        self.get_calls.append(event_id)
        return None if event_id == "missing" else event(event_id)

    async def topics(self, when=None):
        return {
            "supported_topics": ["AI/ML"],
            "supported_areas": [],
            "observed_topics": [],
            "data_mode": "sample",
            "warnings": [],
        }


def test_ids_constrain_candidates_and_report_missing_without_new_search():
    async def run():
        source = FakeSource()
        tools = EventTools(source, now=NOW)
        result = await tools.plan_schedule(event_ids=["sample-1", "missing"])
        assert source.search_calls == []
        assert source.get_calls == ["sample-1", "missing"]
        assert result["missing_event_ids"] == ["missing"]
        assert result["requested_count"] == 2
        assert result["data_mode"] == "sample"
        assert "Fictional" in " ".join(result["warnings"])
        assert [row["event"]["id"] for row in result["selected"]] == ["sample-1"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "arguments",
    [
        {"event_ids": ["sample-1"], "when": "weekend"},
        {"event_ids": []},
        {"event_ids": ["sample-1"] * 11},
        {"event_ids": ["../personal"]},
    ],
)
def test_bad_candidate_arguments_fail_before_source_access(arguments):
    async def run():
        source = FakeSource()
        tools = EventTools(source, now=NOW)
        with pytest.raises(InputError):
            await tools.plan_schedule(**arguments)
        assert source.search_calls == [] and source.get_calls == []

    asyncio.run(run())


def test_candidate_cap_and_truncation_are_visible():
    async def run():
        source = FakeSource()
        result = await EventTools(source, now=NOW).recommend_communities(interests=["AI"])
        assert source.search_calls[0]["limit"] == 50
        assert result["candidate_pool_truncated"] is True
        assert result["total_matching"] == 100

    asyncio.run(run())


def test_search_has_explanations_and_retains_no_private_fields():
    async def run():
        source = FakeSource()
        result = await EventTools(source, now=NOW).search_events(query="AI", free_only=False)
        assert source.search_calls[0]["free"] is False
        assert result["events"][0]["why_matched"]
        assert result["data_mode"] == "sample"
        assert result["returned"] == 1

    asyncio.run(run())


def test_live_cannot_override_current_clock():
    source = FakeSource()
    source.data_mode = "live"
    with pytest.raises(InputError):
        EventTools(source, now=NOW)


def test_unexpected_exception_is_not_exposed_to_client():
    async def run():
        class BrokenSource(FakeSource):
            async def search(self, filters):
                raise RuntimeError("PRIVATE_FAKE_CREDENTIAL")

        with pytest.raises(SourceError) as failure:
            await EventTools(BrokenSource(), now=NOW).search_events()
        assert "PRIVATE_FAKE_CREDENTIAL" not in str(failure.value)

    asyncio.run(run())


def test_sunday_weekend_lower_bound_does_not_spend_limit_on_started_saturday_rows():
    async def run():
        source = FakeSource()
        sunday = datetime.fromisoformat("2026-10-25T08:00:00+05:30")
        await EventTools(source, now=sunday).search_events(when="weekend", limit=5)
        assert datetime.fromisoformat(source.search_calls[0]["dateFrom"]) == sunday

    asyncio.run(run())


def test_elapsed_explicit_discovery_window_returns_empty_without_invalid_upstream_range():
    async def run():
        source = FakeSource()
        result = await EventTools(source, now=NOW).search_events(
            date_from="2026-10-20",
            date_to="2026-10-21",
        )
        assert result["events"] == []
        assert source.search_calls == []

    asyncio.run(run())

import asyncio
from datetime import datetime
from importlib import import_module
from pathlib import Path

import pytest

NOW = datetime.fromisoformat("2026-10-24T08:00:00+05:30")


def core(module):
    path = Path(__file__).parents[1] / "pulseblr_events_mcp" / f"{module}.py"
    assert path.is_file(), f"The {module} event behavior has not been implemented"
    return import_module(f"pulseblr_events_mcp.{module}")


def event(event_id, start="2026-10-24T10:00:00+05:30", end="2026-10-24T11:00:00+05:30", **extra):
    result = {
        "id": event_id,
        "title": f"Fictional event {event_id}",
        "url": f"https://example.com/events/{event_id}",
        "startsAt": start,
        "format": "in-person",
        "organizer": "Fictional Builders",
        "categories": ["AI"],
        "connectionScore": 0,
        "isFree": True,
        "source": "fictional",
        "sourceUrl": f"https://example.com/events/{event_id}",
    }
    if end is not None:
        result["endsAt"] = end
    result.update(extra)
    return result


def selected_ids(result):
    return [row["event"]["id"] for row in result["selected"]]


@pytest.mark.parametrize(
    "clock,start,end",
    [
        ("2026-10-23T23:59:00+05:30", "2026-10-24T00:00:00+05:30", "2026-10-26T00:00:00+05:30"),
        ("2026-10-24T08:00:00+05:30", "2026-10-24T00:00:00+05:30", "2026-10-26T00:00:00+05:30"),
        ("2026-10-25T23:59:00+05:30", "2026-10-24T00:00:00+05:30", "2026-10-26T00:00:00+05:30"),
        ("2026-10-26T00:00:00+05:30", "2026-10-31T00:00:00+05:30", "2026-11-02T00:00:00+05:30"),
    ],
)
def test_weekend_is_current_or_upcoming_ist_saturday_through_sunday(clock, start, end):
    bounds = core("discovery").resolve_window("weekend", now=datetime.fromisoformat(clock))
    assert [bound.isoformat() for bound in bounds] == [start, end]


def test_today_uses_ist_calendar_when_clock_is_utc():
    bounds = core("discovery").resolve_window(
        "today", now=datetime.fromisoformat("2026-10-23T19:00:00+00:00")
    )
    assert [bound.isoformat() for bound in bounds] == [
        "2026-10-24T00:00:00+05:30",
        "2026-10-25T00:00:00+05:30",
    ]


def test_tomorrow_and_rolling_seven_days_have_distinct_boundaries():
    discovery = core("discovery")
    tomorrow = discovery.resolve_window("tomorrow", now=NOW)
    rolling = discovery.resolve_window("rolling7d", now=NOW)
    assert [bound.isoformat() for bound in tomorrow] == [
        "2026-10-25T00:00:00+05:30",
        "2026-10-26T00:00:00+05:30",
    ]
    assert [bound.isoformat() for bound in rolling] == [
        "2026-10-24T08:00:00+05:30",
        "2026-10-31T08:00:00+05:30",
    ]


def test_date_only_range_includes_whole_last_day_but_iso_endpoint_is_exclusive():
    discovery = core("discovery")
    calendar = discovery.resolve_window(date_from="2026-10-24", date_to="2026-10-25", now=NOW)
    exact = discovery.resolve_window(
        date_from="2026-10-24T10:00:00+05:30", date_to="2026-10-25T12:00:00+05:30", now=NOW
    )
    assert [bound.isoformat() for bound in calendar] == [
        "2026-10-24T00:00:00+05:30",
        "2026-10-26T00:00:00+05:30",
    ]
    assert exact[1].isoformat() == "2026-10-25T12:00:00+05:30"


@pytest.mark.parametrize(
    "arguments",
    [
        {"when": "yesterday"},
        {"when": "weekend", "date_from": "2026-10-24"},
        {"date_from": "2026-10-24T08:00:00"},
        {"date_from": "2026-02-30"},
        {"date_from": "2026-10-26", "date_to": "2026-10-24"},
        {"now": datetime(2026, 10, 24, 8)},
    ],
)
def test_invalid_or_ambiguous_date_windows_raise_input_error(arguments):
    discovery = core("discovery")
    error = import_module("pulseblr_events_mcp.errors").InputError
    with pytest.raises(error):
        discovery.resolve_window(**({"now": NOW} | arguments))


def test_filter_excludes_started_and_end_boundary_and_deduplicates_ids():
    rows = [
        event("past", start="2026-10-24T07:59:59+05:30"),
        event("now", start="2026-10-24T08:00:00+05:30"),
        event("now", title="Duplicate"),
        event("last", start="2026-10-25T23:59:59+05:30", end=None),
        event("end", start="2026-10-26T00:00:00+05:30", end=None),
        event("invalid", start="not a date"),
        event("naive", start="2026-10-24T12:00:00"),
    ]
    result = core("discovery").filter_events(
        rows, {"dateFrom": "2026-10-24", "dateTo": "2026-10-25"}, NOW
    )
    assert [row["id"] for row in result] == ["now", "last"]


def test_filter_applies_hard_filters_before_limit_and_preserves_originals():
    wrong = event("wrong", categories=["Cloud"], area="Whitefield")
    match = event("match", title="AI builder meetup", categories=["AI"], area="Indiranagar")
    paid = event("paid", title="AI builder meetup", area="Indiranagar", isFree=False)
    rows = [wrong, match, paid]
    result = core("discovery").filter_events(
        rows,
        {
            "query": "BUILDER",
            "category": "ai",
            "area": "indiranagar",
            "format": "in-person",
            "free": True,
            "limit": 1,
        },
        NOW,
    )
    assert result == [match]
    assert "score" not in match


def test_filter_accepts_upstream_topic_and_area_lists_with_or_matching():
    rows = [
        event("cloud", categories=["Cloud"], area="Whitefield"),
        event("ai", area="Indiranagar"),
        event("wrong-area", area="Koramangala"),
        event("wrong-topic", categories=["Web"], area="Indiranagar"),
    ]
    result = core("discovery").filter_events(
        rows, {"category": ["ai", "cloud"], "area": ["indiranagar", "whitefield"]}, NOW
    )
    assert [row["id"] for row in result] == ["ai", "cloud"]


def test_discovery_query_preserves_upstream_partial_text_matching():
    row = event("kubernetes", title="Kubernetes builders")
    assert core("discovery").filter_events([row], {"query": "kube"}, NOW) == [row]


@pytest.mark.parametrize(
    "query,overrides,expected",
    [
        ("AI Fictional", {"title": "Fictional Practical AI Morning"}, True),
        ("build rust", {"title": "Rustacean systems builders", "categories": []}, True),
        ("rust", {"title": "Trustworthy software", "categories": []}, False),
        ("AI/ML Fictional", {"title": "Fictional workshop", "categories": ["AI/ML"]}, True),
        ("c++", {"title": "C++20 builders", "categories": []}, True),
        ("hall", {"title": "Workshop", "venue": "Fictional Hall", "categories": []}, True),
        ("cloud rust", {"title": "Rust builders", "categories": []}, False),
    ],
)
def test_query_terms_match_source_word_start_prefixes_across_public_fields(
    query, overrides, expected
):
    row = event("query", **overrides)
    result = core("discovery").filter_events([row], {"query": query}, NOW)
    assert result == ([row] if expected else [])


def test_multiword_query_survives_sample_source_and_all_discovery_consumers():
    async def run():
        from pulseblr_events_mcp.service import EventTools
        from pulseblr_events_mcp.sources import SampleSource

        tools = EventTools(SampleSource(), now=NOW)
        result = await tools.search_events(query="AI Fictional", limit=50)
        assert result["total_matching"] == 7
        assert {row["id"] for row in result["events"]} == {
            "sample-ai-long",
            "sample-missing-end",
            "sample-ai-sunday",
            "sample-ai-morning",
            "sample-oss-afternoon",
            "sample-overlap",
            "sample-online-two",
        }
        communities = await tools.recommend_communities(query="AI Fictional")
        assert communities["communities"]
        plan = await tools.plan_schedule(query="AI Fictional")
        assert plan["selected"]
        assert plan["needs_duration"][0]["event"]["id"] == "sample-missing-end"

    asyncio.run(run())


def test_filter_requires_explicit_true_for_listed_free():
    known = event("known")
    unknown = event("unknown", isFree=None)
    missing = event("missing")
    missing.pop("isFree")
    assert [
        row["id"]
        for row in core("discovery").filter_events([unknown, missing, known], {"free": True}, NOW)
    ] == ["known"]


def test_unknown_area_returns_no_events_instead_of_guessing():
    assert (
        core("discovery").filter_events(
            [event("a", area="Indiranagar")], {"area": "Unlisted area"}, NOW
        )
        == []
    )


def test_upstream_connections_sort_applies_before_limit():
    rows = [
        event("soon", connectionScore=1),
        event(
            "connected",
            start="2026-10-25T10:00:00+05:30",
            end="2026-10-25T11:00:00+05:30",
            connectionScore=90,
        ),
    ]
    result = core("discovery").filter_events(rows, {"sort": "connections", "limit": 1}, NOW)
    assert [row["id"] for row in result] == ["connected"]


def test_relevance_order_from_upstream_survives_local_hard_filtering():
    rows = [
        event("relevant", start="2026-10-25T10:00:00+05:30", end="2026-10-25T11:00:00+05:30"),
        event("soon"),
    ]
    result = core("discovery").filter_events(rows, {"sort": "relevance", "limit": 1}, NOW)
    assert [row["id"] for row in result] == ["relevant"]


def test_community_groups_case_and_spacing_and_keeps_observed_evidence():
    rows = [
        event("a", organizer=" Fictional  Builders "),
        event("b", organizer="fictional builders"),
        event("c", organizer=None),
    ]
    result = core("discovery").recommend_communities(rows, ["AI"], limit=3)
    assert len(result["communities"]) == 1
    community = result["communities"][0]
    assert community["organizer"] == "Fictional Builders"
    assert community["observed_event_count"] == 2
    assert community["matched_interests"] == ["AI"]
    assert {row["id"] for row in community["representative_events"]} == {"a", "b"}
    assert "contact" not in community and "membership_url" not in community
    assert result["warnings"]


def test_community_omits_unknown_organizers_and_does_not_hallucinate_membership():
    result = core("discovery").recommend_communities(
        [event("a", organizer=""), event("b", organizer=None)]
    )
    assert result["communities"] == []
    assert result["warnings"]


def test_community_interest_match_beats_unrelated_title_substrings():
    rows = [
        event("chair", title="Chair design", organizer="Chairs", categories=[]),
        event("ai", title="AI meetup", organizer="Builders", categories=["AI"]),
    ]
    result = core("discovery").recommend_communities(rows, ["AI"], limit=1)
    assert result["communities"][0]["organizer"] == "Builders"


def test_planner_uses_exact_subset_instead_of_greedy_single_event():
    rows = [
        event(
            "long",
            start="2026-10-24T09:00:00+05:30",
            end="2026-10-24T17:00:00+05:30",
            connectionScore=100,
        ),
        event(
            "morning",
            start="2026-10-24T09:00:00+05:30",
            end="2026-10-24T11:00:00+05:30",
            connectionScore=60,
        ),
        event(
            "afternoon",
            start="2026-10-24T12:00:00+05:30",
            end="2026-10-24T14:00:00+05:30",
            connectionScore=60,
        ),
    ]
    result = core("planner").plan_schedule(rows, max_events=2, now=NOW)
    assert selected_ids(result) == ["morning", "afternoon"]
    assert result["total_score"] == 120
    rejected = result["not_selected"][0]
    assert rejected["reason_code"] == "schedule_conflict"
    assert set(rejected["conflicts_with"]) == {"morning", "afternoon"}


@pytest.mark.parametrize("gap,expected", [(59, ["a"]), (60, ["a", "b"])])
def test_physical_transfer_exact_equality_is_feasible(gap, expected):
    minute = gap % 60
    hour = 11 + gap // 60
    rows = [
        event("a", connectionScore=10),
        event(
            "b",
            start=f"2026-10-24T{hour:02}:{minute:02}:00+05:30",
            end="2026-10-24T15:00:00+05:30",
            connectionScore=9,
        ),
    ]
    assert selected_ids(core("planner").plan_schedule(rows, now=NOW)) == expected


@pytest.mark.parametrize(
    "format_b,gap,expected", [("online", 4, 1), ("online", 5, 2), ("hybrid", 5, 1)]
)
def test_only_two_online_events_use_five_minute_switching_buffer(format_b, gap, expected):
    rows = [
        event("a", format="online", connectionScore=10),
        event(
            "b",
            format=format_b,
            start=f"2026-10-24T11:{gap:02}:00+05:30",
            end="2026-10-24T13:00:00+05:30",
            connectionScore=9,
        ),
    ]
    result = core("planner").plan_schedule(rows, now=NOW)
    assert len(result["selected"]) == expected


def test_cross_midnight_transfer_uses_real_datetime_not_clock_time():
    rows = [
        event("a", start="2026-10-24T22:00:00+05:30", end="2026-10-24T23:30:00+05:30"),
        event("b", start="2026-10-25T00:30:00+05:30", end="2026-10-25T01:30:00+05:30"),
    ]
    assert selected_ids(core("planner").plan_schedule(rows, now=NOW)) == ["a", "b"]


@pytest.mark.parametrize(
    "end", [None, "invalid", "2026-10-24T09:00:00+05:30", "2026-10-24T10:00:00+05:30"]
)
def test_strict_policy_excludes_untrusted_duration_and_reports_needs_duration(end):
    result = core("planner").plan_schedule([event("missing", end=end)], now=NOW)
    assert result["selected"] == []
    assert result["needs_duration"][0]["event"]["id"] == "missing"
    assert result["not_selected"][0]["reason_code"] == "needs_duration"
    assert result["warnings"]


def test_normalized_invalid_end_marker_preserves_needs_duration_reason():
    row = event("invalid-end", end=None, endTimeStatus="invalid")
    result = core("planner").plan_schedule([row], now=NOW)
    assert result["needs_duration"][0]["reason_code"] == "invalid_end"


def test_explicit_estimation_makes_schedule_conditional_and_does_not_mutate_source():
    source = event("estimate", end=None)
    result = core("planner").plan_schedule(
        [source], duration_policy="estimate", assumed_duration_minutes=90, now=NOW
    )
    assert selected_ids(result) == ["estimate"]
    assert result["selected"][0]["duration_estimated"] is True
    assert result["selected"][0]["effective_ends_at"] == "2026-10-24T11:30:00+05:30"
    assert result["conditional_on_assumptions"] is True
    assert result["warnings"] and result["assumptions"]
    assert "endsAt" not in source


@pytest.mark.parametrize(
    "options",
    [
        {"max_events": 0},
        {"max_events": 4},
        {"max_events": True},
        {"transfer_buffer_minutes": -1},
        {"transfer_buffer_minutes": float("inf")},
        {"duration_policy": "guess"},
        {"duration_policy": {}},
        {"duration_policy": "estimate"},
        {"duration_policy": "estimate", "assumed_duration_minutes": 0},
        {"duration_policy": "strict", "assumed_duration_minutes": 60},
        {"interests": "AI"},
    ],
)
def test_planner_rejects_invalid_constraints(options):
    planner = core("planner")
    error = import_module("pulseblr_events_mcp.errors").InputError
    with pytest.raises(error):
        planner.plan_schedule([event("a")], now=NOW, **options)


def test_planner_rejects_more_than_fifty_input_candidates():
    planner = core("planner")
    error = import_module("pulseblr_events_mcp.errors").InputError
    with pytest.raises(error):
        planner.plan_schedule([event(str(index)) for index in range(51)], now=NOW)


def test_planner_discards_started_invalid_start_and_duplicate_events():
    rows = [
        event("past", start="2026-10-24T07:59:00+05:30"),
        event("invalid", start="bad"),
        event("valid"),
        event("valid"),
    ]
    result = core("planner").plan_schedule(rows, now=NOW)
    assert selected_ids(result) == ["valid"]
    reasons = {row["event"]["id"]: row["reason_code"] for row in result["not_selected"]}
    assert reasons == {"past": "already_started", "invalid": "invalid_start"}
    assert result["candidate_count"] == 3
    assert result["warnings"]


def test_event_cap_is_distinguished_from_a_time_conflict():
    rows = [
        event("a", connectionScore=10),
        event(
            "b",
            start="2026-10-24T12:00:00+05:30",
            end="2026-10-24T13:00:00+05:30",
            connectionScore=5,
        ),
    ]
    result = core("planner").plan_schedule(rows, max_events=1, now=NOW)
    assert selected_ids(result) == ["a"]
    assert result["not_selected"][0]["reason_code"] == "event_cap"


def test_interest_ranking_prefers_category_evidence_and_is_not_a_probability():
    rows = [
        event("generic", categories=["Cloud"], connectionScore=5),
        event("relevant", categories=["AI"], connectionScore=5),
    ]
    result = core("planner").plan_schedule(rows, interests=["AI"], max_events=1, now=NOW)
    assert selected_ids(result) == ["relevant"]
    assert result["selected"][0]["matched_interests"] == ["AI"]
    assert result["selected"][0]["score"] > 5
    assert "probability" not in result["selected"][0]


def test_ties_are_stable_under_input_reversal():
    rows = [event("z"), event("a")]
    planner = core("planner")
    assert selected_ids(planner.plan_schedule(rows, max_events=1, now=NOW)) == ["a"]
    assert selected_ids(planner.plan_schedule(list(reversed(rows)), max_events=1, now=NOW)) == ["a"]


def test_empty_candidate_set_is_an_honest_empty_schedule():
    result = core("planner").plan_schedule([], now=NOW)
    assert result["selected"] == []
    assert result["not_selected"] == []
    assert result["candidate_count"] == 0
    assert result["conditional_on_assumptions"] is False


def test_impossible_transfer_near_calendar_maximum_reports_conflict_without_overflow():
    rows = [
        event(
            "a",
            start="9999-12-31T22:00:00+05:30",
            end="9999-12-31T23:30:00+05:30",
            connectionScore=10,
        ),
        event(
            "b",
            start="9999-12-31T23:40:00+05:30",
            end="9999-12-31T23:50:00+05:30",
            connectionScore=9,
        ),
    ]
    result = core("planner").plan_schedule(rows, now=NOW)
    assert selected_ids(result) == ["a"]
    assert result["not_selected"][0]["reason_code"] == "schedule_conflict"


@pytest.mark.parametrize(
    "signal,score",
    [
        (10**1000, 100),
        (-(10**1000), 0),
        (float("nan"), 0),
        (float("inf"), 0),
        (True, 0),
        ("high", 0),
    ],
    ids=["huge-positive", "huge-negative", "nan", "infinite", "boolean", "string"],
)
def test_malformed_or_oversized_connection_signals_cannot_break_ranking(signal, score):
    result = core("planner").plan_schedule([event("a", connectionScore=signal)], now=NOW)
    assert result["selected"][0]["score"] == score

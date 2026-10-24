"""Run practical, public-only review scenarios through the official MCP stdio client."""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED_TOOLS = {
    "search_events",
    "get_event",
    "list_topics",
    "recommend_communities",
    "plan_schedule",
}
SAMPLE_CLOCK = "2026-10-24T08:00:00+05:30"
PUBLIC_ENDPOINT = "https://pulseblr-u9f1.vercel.app/api/mcp"
ROOT = Path(__file__).resolve().parents[1]


class CheckFailure(Exception):
    """An assertion with a safe, reviewer-facing explanation."""


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def instant(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except ValueError:
        return None


def words(value):
    return " ".join(re.sub(r"[^\w]+", " ", str(value).casefold()).split())


def event_summary(event):
    return {
        key: event[key]
        for key in (
            "id",
            "title",
            "url",
            "startsAt",
            "endsAt",
            "endTimeStatus",
            "format",
            "area",
            "organizer",
            "categories",
            "isFree",
        )
        if key in event
    }


def unknown_duration(event):
    start, end = instant(event.get("startsAt")), instant(event.get("endsAt"))
    return start is None or end is None or end <= start


def check_public_event(event, source):
    require(isinstance(event, dict) and bool(event.get("id")), "Event must have a public ID.")
    require(bool(event.get("title")), "Event must have a title.")
    parsed = urlsplit(event.get("url", ""))
    require(parsed.scheme == "https" and bool(parsed.hostname), "Event link must be HTTPS.")
    require(not parsed.username and not parsed.password, "Public link must not have credentials.")
    require(instant(event.get("startsAt")) is not None, "Start must include a timezone.")
    require(event.get("format") in {"online", "offline", "hybrid"}, "Unknown event format.")
    if source == "live":
        require(parsed.hostname != "example.com", "Live results must not use sample event links.")
        require(not str(event["id"]).startswith("sample-"), "Live results must not use sample IDs.")


def check_search(payload, source, expected):
    events, filters = payload["events"], payload["filters"]
    require(len(events) <= expected.get("limit", 10), "Search exceeded its requested limit.")
    require(payload["returned"] == len(events), "Returned count differs from event count.")
    require(len({event["id"] for event in events}) == len(events), "Duplicate event IDs returned.")
    start, end = instant(filters["dateFrom"]), instant(filters["dateTo"])
    require(start is not None and end is not None, "Filter boundaries must include timezones.")
    for public_key, requested_key in (
        ("category", "topics"),
        ("area", "areas"),
        ("format", "format"),
        ("free", "free_only"),
        ("limit", "limit"),
    ):
        if requested_key in expected:
            require(filters.get(public_key) == expected[requested_key], "Requested filter changed.")
    for event in events:
        check_public_event(event, source)
        require(start <= instant(event["startsAt"]) < end, "Event is outside returned time bounds.")
        if "topics" in expected:
            require(
                bool(
                    {words(v) for v in expected["topics"]}
                    & {words(v) for v in event.get("categories", [])}
                ),
                "Event does not match the topic filter.",
            )
        if "areas" in expected:
            require(
                words(event.get("area")) in {words(v) for v in expected["areas"]},
                "Event does not match the area filter.",
            )
        if "format" in expected:
            require(event["format"] == expected["format"], "Event does not match format.")
        if expected.get("free_only"):
            require(event.get("isFree") is True, "Event is not explicitly listed free.")
    return {
        "returned": len(events),
        "filters": filters,
        "total_matching": payload.get("total_matching"),
        "candidate_pool_truncated": payload.get("candidate_pool_truncated"),
        "events": [event_summary(event) for event in events],
        "zero_is_valid": True,
    }


def child_environment():
    names = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "TZ",
    }
    return {name: os.environ.get(name, "") for name in names} | {
        "PATH": os.environ.get("PATH", os.defpath),
    }


async def review(source):
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "data_notice": (
            "Anonymous public live listings; retrieval is not independent verification."
            if source == "live"
            else "FICTIONAL offline sample events; not real listings."
        ),
        "public_endpoint": PUBLIC_ENDPOINT if source == "live" else None,
        "sample_clock": SAMPLE_CLOCK if source == "sample" else None,
        "client": "Official mcp.ClientSession over stdio; no direct tool-function calls.",
        "python_version": sys.version.split()[0],
        "gemini": "Not invoked by this harness. MCP results do not establish model generation.",
        "limits": {
            "search_limit": 10,
            "explicit_id_batch_limit": 5,
            "max_selected_events": 2,
            "physical_transfer_minutes": 60,
            "online_to_online_minutes": 5,
            "duration_policy": "strict",
            "retries": 0,
        },
        "scenarios": [],
    }
    state = {}
    args = ["-m", "pulseblr_events_mcp", "--source", source]
    if source == "sample":
        args += ["--now", SAMPLE_CLOCK]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=args,
        cwd=ROOT,
        env=child_environment(),
    )

    async def scenario(name, action):
        started = time.monotonic()
        try:
            evidence = await action()
            status = "skipped" if evidence.pop("skipped", False) else "passed"
            result = {"scenario": name, "status": status, "evidence": evidence}
        except CheckFailure as error:
            result = {"scenario": name, "status": "failed", "reason": str(error)}
        except Exception:
            result = {
                "scenario": name,
                "status": "failed",
                "reason": "MCP operation could not complete; no raw exception or credentials logged.",
            }
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["scenarios"].append(result)
        print(f"{result['status'].upper():7} {name}", flush=True)

    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=120) as session:

            async def call(name, arguments):
                result = await session.call_tool(name, arguments, read_timeout_seconds=120)
                require(not result.is_error, f"{name} returned an MCP tool error.")
                payload = result.structured_content
                require(isinstance(payload, dict), "Tool response must be structured JSON.")
                require(payload.get("data_mode") == source, "Tool returned the wrong data mode.")
                require(
                    instant(payload.get("fetched_at")) is not None,
                    "Tool response must include retrieval time.",
                )
                require(bool(payload.get("warnings")), "Tool must preserve source warnings.")
                if source == "sample":
                    require(
                        "fictional" in " ".join(payload["warnings"]).casefold(),
                        "Sample results must carry fictional-data warnings.",
                    )
                return payload

            async def protocol():
                initialized = await session.initialize()
                listing = await session.list_tools()
                names = {tool.name for tool in listing.tools}
                state["tool_names"] = names
                require(names == EXPECTED_TOOLS, "Server must advertise exactly five public tools.")
                require(listing.next_cursor is None, "Unexpected additional tool page.")
                require(
                    all(
                        tool.annotations
                        and tool.annotations.read_only_hint
                        and not tool.annotations.destructive_hint
                        for tool in listing.tools
                    ),
                    "All tools must advertise read-only, non-destructive behavior.",
                )
                return {"protocol_version": initialized.protocol_version, "tools": sorted(names)}

            await scenario("01_protocol_and_read_only_surface", protocol)

            async def topics():
                payload = await call("list_topics", {"when": "weekend"})
                for key in ("supported_topics", "supported_areas"):
                    require(
                        isinstance(payload.get(key), list) and bool(payload[key]),
                        "Supported vocabulary must be a nonempty list.",
                    )
                state["topics"] = payload
                return {
                    key: payload[key]
                    for key in (
                        "supported_topics",
                        "supported_areas",
                        "observed_topics",
                        "total_events",
                        "window",
                        "counts_truncated",
                        "fetched_at",
                    )
                }

            await scenario("02_discover_supported_topics_and_areas", topics)

            async def narrow_search():
                vocabulary = state.get("topics", {})
                topic = next(
                    (
                        value
                        for value in vocabulary.get("supported_topics", [])
                        if "ai" in words(value).split()
                    ),
                    None,
                )
                area = next(
                    (
                        value
                        for value in vocabulary.get("supported_areas", [])
                        if words(value) == "koramangala"
                    ),
                    None,
                )
                require(
                    topic is not None and area is not None,
                    "Public vocabulary did not advertise AI and Koramangala filters.",
                )
                arguments = {
                    "topics": [topic],
                    "areas": [area],
                    "when": "weekend",
                    "format": "offline",
                    "free_only": True,
                    "limit": 10,
                }
                payload = await call("search_events", arguments)
                state["narrow"] = payload
                return {
                    "arguments": arguments,
                    "fetched_at": payload["fetched_at"],
                    **check_search(payload, source, arguments),
                }

            await scenario("03_weekend_ai_free_in_person_koramangala", narrow_search)

            async def broad_search():
                arguments = {"when": "week", "limit": 10}
                payload = await call("search_events", arguments)
                evidence = check_search(payload, source, arguments)
                state["broad"] = payload
                candidates = payload["events"][:5]
                missing_end = next(
                    (event for event in payload["events"] if unknown_duration(event)), None
                )
                if missing_end and missing_end["id"] not in {event["id"] for event in candidates}:
                    candidates = candidates[:4] + [missing_end]
                state["candidates"] = {event["id"]: event for event in candidates}
                return {
                    "arguments": arguments,
                    "fetched_at": payload["fetched_at"],
                    **evidence,
                    "explicit_candidate_ids": list(state["candidates"]),
                    "reason": "Broader week candidates; an empty narrow search is legitimate.",
                }

            await scenario("04_broader_week_candidates", broad_search)

            async def detail():
                ids = list(state.get("candidates", {}))
                if not ids:
                    return {"skipped": True, "reason": "No live candidate ID; no event invented."}
                payload = await call("get_event", {"event_id": ids[0]})
                require(payload.get("found") is True, "First searched event was not resolved.")
                check_public_event(payload["event"], source)
                require(payload["event"]["id"] == ids[0], "Details changed event identity.")
                return {
                    "event": event_summary(payload["event"]),
                    "fetched_at": payload["fetched_at"],
                }

            await scenario("05_get_first_public_event_details", detail)

            async def communities():
                candidates = state.get("candidates", {})
                if not candidates:
                    return {
                        "skipped": True,
                        "reason": "No candidate IDs for evidence-based groups.",
                    }
                arguments = {
                    "event_ids": list(candidates),
                    "interests": ["AI", "Open Source"],
                    "limit": 3,
                }
                payload = await call("recommend_communities", arguments)
                require(len(payload["communities"]) <= 3, "Community limit exceeded.")
                for group in payload["communities"]:
                    require(
                        set(group)
                        <= {
                            "organizer",
                            "observed_event_count",
                            "matched_interests",
                            "score",
                            "representative_events",
                            "reason",
                        },
                        "Unexpected community fields could imply unsupported membership/contact data.",
                    )
                    require(bool(group["representative_events"]), "Group lacks event evidence.")
                    for event in group["representative_events"]:
                        require(event["id"] in candidates, "Group used an unrequested event.")
                        original = candidates[event["id"]]
                        require(event["url"] == original["url"], "Group invented an event link.")
                        require(
                            words(group["organizer"]) == words(original.get("organizer")),
                            "Group organizer is absent from its candidate event.",
                        )
                require(
                    "not a membership directory" in payload.get("scope", ""),
                    "Community scope must disavow membership-directory claims.",
                )
                return {
                    "arguments": arguments,
                    "communities": payload["communities"],
                    "scope": payload["scope"],
                    "missing_event_ids": payload["missing_event_ids"],
                    "warnings": payload["warnings"],
                }

            await scenario("06_organiser_recommendations_from_explicit_ids", communities)

            async def schedule():
                candidates = state.get("candidates", {})
                if not candidates:
                    return {"skipped": True, "reason": "No candidates; no schedule invented."}
                arguments = {
                    "event_ids": list(candidates),
                    "interests": ["AI", "Open Source"],
                    "max_events": 2,
                    "transfer_buffer_minutes": 60,
                    "duration_policy": "strict",
                }
                payload = await call("plan_schedule", arguments)
                selected = payload["selected"]
                require(len(selected) <= 2, "Selected more than two events.")
                require(
                    payload["conditional_on_assumptions"] is False,
                    "Strict schedule must not estimate missing durations.",
                )
                observed = {}
                for key in ("selected", "not_selected", "needs_duration"):
                    for row in payload[key]:
                        event = row["event"]
                        require(event["id"] in candidates, "Plan used an unrequested event.")
                        check_public_event(event, source)
                        observed[event["id"]] = event
                missing_ids = set(payload["missing_event_ids"])
                require(missing_ids <= set(candidates), "Missing IDs were not requested.")
                require(
                    set(observed) | missing_ids == set(candidates),
                    "Plan did not account for every requested candidate.",
                )
                needs_ids = {row["event"]["id"] for row in payload["needs_duration"]}
                already_started = {
                    row["event"]["id"]
                    for row in payload["not_selected"]
                    if row["reason_code"] == "already_started"
                }
                expected_unknowns = {
                    event_id for event_id, event in observed.items() if unknown_duration(event)
                } - already_started
                require(
                    needs_ids == expected_unknowns,
                    "Strict plan did not report every unknown/invalid end.",
                )
                for row in selected:
                    require(
                        not unknown_duration(row["event"]), "Selected event lacks valid duration."
                    )
                    require(row["duration_estimated"] is False, "Strict duration was estimated.")
                    require(
                        instant(row["effective_ends_at"]) == instant(row["event"]["endsAt"]),
                        "Effective end differs from the published end in strict mode.",
                    )
                pair_checks = []
                for left, right in zip(selected, selected[1:]):
                    online = left["event"]["format"] == right["event"]["format"] == "online"
                    required_minutes = 5 if online else 60
                    gap = (
                        instant(right["event"]["startsAt"]) - instant(left["effective_ends_at"])
                    ).total_seconds() / 60
                    require(
                        gap >= required_minutes, "Selected pair violates its transfer allowance."
                    )
                    pair_checks.append(
                        {
                            "from": left["event"]["id"],
                            "to": right["event"]["id"],
                            "gap_minutes": gap,
                            "required_minutes": required_minutes,
                        }
                    )
                sample_online_pair_check = None
                if source == "sample":
                    online_ids = [
                        event["id"]
                        for event in state["broad"]["events"]
                        if event["format"] == "online" and not unknown_duration(event)
                    ][:2]
                    require(len(online_ids) == 2, "Offline fixture lacks its two online examples.")
                    online_plan = await call(
                        "plan_schedule", {**arguments, "event_ids": online_ids}
                    )
                    online_selected = online_plan["selected"]
                    require(len(online_selected) == 2, "Five-minute online pair was not selected.")
                    left, right = online_selected
                    gap = (
                        instant(right["event"]["startsAt"]) - instant(left["effective_ends_at"])
                    ).total_seconds() / 60
                    require(gap == 5, "Offline online pair must exercise the five-minute boundary.")
                    sample_online_pair_check = {
                        "fictional": True,
                        "selected_ids": online_ids,
                        "gap_minutes": gap,
                        "required_minutes": 5,
                    }
                return {
                    "arguments": arguments,
                    "selected": [event_summary(row["event"]) for row in selected],
                    "needs_duration": [
                        {"id": row["event"]["id"], "reason": row["reason_code"]}
                        for row in payload["needs_duration"]
                    ],
                    "search_snapshot_unknown_end_ids": [
                        event_id
                        for event_id, event in candidates.items()
                        if unknown_duration(event)
                    ],
                    "missing_event_ids": sorted(missing_ids),
                    "not_selected": [
                        {"id": row["event"]["id"], "reason": row["reason_code"]}
                        for row in payload["not_selected"]
                    ],
                    "pair_checks": pair_checks,
                    "sample_online_pair_check": sample_online_pair_check,
                    "pair_check_notice": (
                        "Validated all selected adjacent pairs."
                        if pair_checks
                        else "No pair selected; no live pair feasibility claim."
                    ),
                    "assumptions": payload["assumptions"],
                    "warnings": payload["warnings"],
                }

            await scenario("07_strict_schedule_identity_duration_and_buffers", schedule)

            async def no_match():
                arguments = {
                    "query": "zzzzpulseblrreviewnomatch7d9c4e21",
                    "when": "week",
                    "limit": 10,
                }
                payload = await call("search_events", arguments)
                require(
                    payload["events"] == [] and payload["returned"] == 0,
                    "Unique no-match query returned events.",
                )
                return {"arguments": arguments, "returned": 0, "fetched_at": payload["fetched_at"]}

            await scenario("08_no_match_is_an_empty_result", no_match)

            async def invalid_cap():
                result = await session.call_tool("plan_schedule", {"max_events": 99})
                require(result.is_error, "Invalid max_events=99 must be rejected.")
                return {"arguments": {"max_events": 99}, "is_error": True}

            await scenario("09_invalid_event_cap_rejected", invalid_cap)

            async def private_tool():
                require(
                    "my_people" not in state.get("tool_names", set()),
                    "Personal tool must not be advertised.",
                )
                result = await session.call_tool("my_people", {})
                require(result.is_error, "Unknown personal tool name must be rejected locally.")
                return {
                    "tool": "my_people",
                    "is_error": True,
                    "scope": "Unknown-name request to this local server only; no personal backend read.",
                }

            await scenario("10_personal_tool_name_rejected_locally", private_tool)

    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {
        status: sum(row["status"] == status for row in report["scenarios"])
        for status in ("passed", "failed", "skipped")
    }
    report["warnings"] = [
        "No Gemini or other model API was called; no private environment file was loaded.",
        "Live events can change between calls. Free status, registration and freshness are unverified.",
        "Pair-buffer assertions only exercise pairs actually selected; sample mode supplies known durations.",
        "One run bounds upstream reads to 16 public operations plus MCP handshakes, with no retries; do not loop rapidly against the 120/minute service.",
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("live", "sample"), default="live")
    parser.add_argument(
        "--output",
        type=Path,
        help="Save the report. Default: docs/review_results.json for live, review_results.sample.json for sample.",
    )
    args = parser.parse_args()
    output = args.output or ROOT / "docs" / (
        "review_results.json" if args.source == "live" else "review_results.sample.json"
    )
    try:
        report = asyncio.run(review(args.source))
    except Exception:
        print(
            "Review could not initialize/close the MCP session; no raw errors printed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(
        f"{args.source}: {summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['skipped']} skipped. Report: {output}"
    )
    raise SystemExit(1 if summary["failed"] else 0)


if __name__ == "__main__":
    main()

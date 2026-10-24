"""
backend_test.py - Planning Puppet: backend verification suite.

Tests every layer of the agent stack WITHOUT a running server:
  1. Environment / API key check
  2. All four deterministic tool functions (no API call needed)
  3. Gemini API connectivity via the evaluator (requires GEMINI_API_KEY)
  4. Full ADK agent round-trip with tool calling (requires GEMINI_API_KEY)

Usage
-----
    # From agents/planning-puppet/ with the venv activated:
    python backend_test.py

    # Skip the live API tests (offline / CI mode):
    python backend_test.py --offline
"""

from __future__ import annotations

import json
import os
import sys
import asyncio
import argparse
from typing import Any

# ── Colour helpers (no extra dependencies) ──────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}[PASS]{RESET}  {msg}")
def fail(msg: str) -> None: print(f"  {RED}[FAIL]{RESET}  {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}[WARN]{RESET}  {msg}")
def info(msg: str) -> None: print(f"  {CYAN}[INFO]{RESET}  {msg}")

def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'-'*55}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'-'*55}{RESET}")

# ── Counters ─────────────────────────────────────────────────────────────────
passed = 0
failed = 0

def assert_equal(label: str, actual: Any, expected: Any) -> bool:
    global passed, failed
    if actual == expected:
        ok(f"{label}: {actual!r}")
        passed += 1
        return True
    else:
        fail(f"{label}: expected {expected!r}, got {actual!r}")
        failed += 1
        return False

def assert_true(label: str, condition: bool, detail: str = "") -> bool:
    global passed, failed
    if condition:
        ok(f"{label}" + (f" — {detail}" if detail else ""))
        passed += 1
        return True
    else:
        fail(f"{label}" + (f" — {detail}" if detail else ""))
        failed += 1
        return False

def assert_in(label: str, key: Any, container: Any) -> bool:
    global passed, failed
    if key in container:
        ok(f"{label}: '{key}' present")
        passed += 1
        return True
    else:
        fail(f"{label}: '{key}' missing from {type(container).__name__}")
        failed += 1
        return False


# ============================================================================
# TEST SECTION 1 – Environment
# ============================================================================

def test_environment(offline: bool) -> bool:
    section("1 · Environment & API Key Check")
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "")

    if not api_key or api_key == "your_gemini_api_key_here":
        if offline:
            warn("GEMINI_API_KEY not set – running in offline mode (API tests skipped).")
            return False
        else:
            fail("GEMINI_API_KEY is missing. Copy .env.example to .env and add your key.")
            fail("Re-run with --offline to skip live API tests.")
            sys.exit(1)

    ok(f"GEMINI_API_KEY detected (starts with: {api_key[:8]}…)")
    model = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite")
    ok(f"MODEL_NAME = {model}")
    evaluator_model = os.getenv("EVALUATOR_MODEL", model)
    ok(f"EVALUATOR_MODEL = {evaluator_model}")

    if offline:
        warn("Running in --offline mode: skipping live Gemini API tests.")
        return False

    return True


# ============================================================================
# TEST SECTION 2 – Deterministic Tool Functions (no API)
# ============================================================================

def test_tools() -> None:
    section("2 · Deterministic Tool Functions (no API required)")

    from tools import (
        calculate_budget_breakdown,
        generate_event_timeline,
        get_vendor_checklist,
        generate_pinterest_inspiration,
        search_event_venues,
    )

    # ── Tool 1: calculate_budget_breakdown ───────────────────────────────────
    info("Tool 1 – calculate_budget_breakdown")

    # Wedding
    r = calculate_budget_breakdown("wedding", 20000.0, 100)
    assert_in("wedding result has 'line_items'",    "line_items",            r)
    assert_in("wedding result has 'per_guest_spend_usd'", "per_guest_spend_usd", r)
    assert_equal("wedding per-guest spend",         r["per_guest_spend_usd"], 200.0)
    assert_true("wedding has 6 line items",         len(r["line_items"]) == 6,
                f"got {len(r['line_items'])}")
    total_check = round(sum(i["amount_usd"] for i in r["line_items"]), 2)
    assert_equal("wedding line items sum to budget", total_check, 20000.0)
    assert_true("wedding has tips",                 len(r.get("tips", [])) > 0)

    # Birthday
    r2 = calculate_budget_breakdown("birthday", 5000.0, 50)
    assert_in("birthday result has 'line_items'",  "line_items", r2)
    assert_equal("birthday per-guest spend",        r2["per_guest_spend_usd"], 100.0)

    # Community
    r3 = calculate_budget_breakdown("community", 10000.0, 200)
    assert_in("community result has 'line_items'", "line_items", r3)

    # Error handling
    r_err = calculate_budget_breakdown("concert", 5000.0, 50)
    assert_in("unknown type returns error",          "error", r_err)

    # ── Tool 2: generate_event_timeline ─────────────────────────────────────
    info("Tool 2 – generate_event_timeline")

    r = generate_event_timeline("wedding", "2027-06-15")
    assert_in("timeline has 'planning_phases'",    "planning_phases", r)
    assert_equal("timeline has 4 phases",           len(r["planning_phases"]), 4)
    assert_in("timeline has 'days_until_event'",   "days_until_event", r)
    assert_true("days_until_event is positive int", isinstance(r["days_until_event"], int)
                and r["days_until_event"] > 0,
                str(r["days_until_event"]))

    r2 = generate_event_timeline("birthday")        # no date
    assert_true("no-date timeline still has phases", "planning_phases" in r2)
    assert_true("no-date days_until is None",        r2["days_until_event"] is None)

    r_err = generate_event_timeline("concert", "2027-01-01")
    assert_in("unknown event type returns error",  "error", r_err)

    r_bad = generate_event_timeline("wedding", "not-a-date")
    assert_in("bad date returns error",            "error", r_bad)

    # ── Tool 3: get_vendor_checklist ─────────────────────────────────────────
    info("Tool 3 – get_vendor_checklist")

    r = get_vendor_checklist("wedding", "large")
    assert_in("vendor checklist has 'required_vendors'",   "required_vendors",        r)
    assert_in("vendor checklist has 'booking_deadlines'",  "booking_deadlines",       r)
    assert_in("vendor checklist has 'key_questions_by_vendor'", "key_questions_by_vendor", r)
    assert_true("large wedding has 10+ vendors",           len(r["required_vendors"]) >= 10,
                str(len(r["required_vendors"])))

    r2 = get_vendor_checklist("birthday", "small")
    assert_true("small birthday checklist present",        len(r2["required_vendors"]) > 0)

    # scale fallback
    r3 = get_vendor_checklist("community", "medium")    # 'medium' → defaults to 'large'
    assert_true("scale fallback works",                    "required_vendors" in r3)

    # ── Tool 4: generate_pinterest_inspiration ───────────────────────────────
    info("Tool 4 – generate_pinterest_inspiration")

    r = generate_pinterest_inspiration("wedding", "boho")
    assert_in("inspiration has 'pinterest_links'",   "pinterest_links",  r)
    assert_in("inspiration has 'matched_theme'",     "matched_theme",    r)
    assert_equal("boho theme matched",               r["matched_theme"], "boho")
    assert_true("has 5 pinterest links",             len(r["pinterest_links"]) == 5,
                str(len(r["pinterest_links"])))
    assert_true("link is markdown format",
                r["pinterest_links"][0].startswith("["),
                r["pinterest_links"][0][:30])
    assert_true("link contains pinterest URL",
                "pinterest.com" in r["pinterest_links"][0],
                r["pinterest_links"][0])

    r2 = generate_pinterest_inspiration("birthday", "tropical")
    assert_equal("tropical birthday matched",       r2["matched_theme"], "tropical")

    # fuzzy match test
    r3 = generate_pinterest_inspiration("community", "eco-friendly sustainability")
    assert_equal("fuzzy eco theme matched",         r3["matched_theme"], "eco")

    # fallback to first theme when no match
    r4 = generate_pinterest_inspiration("wedding", "underwater")
    assert_true("unknown theme falls back gracefully", "matched_theme" in r4)

    r_err = generate_pinterest_inspiration("gala", "modern")
    assert_in("unknown event type returns error",  "error", r_err)

    # ── Tool 5: search_event_venues ──────────────────────────────────────────
    info("Tool 5 – search_event_venues (Google Maps Places API)")
    venues_res = search_event_venues("boho garden wedding venue", "Bangalore")
    assert_in("venue search has 'venues'",         "venues", venues_res)
    assert_in("venue search has 'maps_search_url'","maps_search_url", venues_res)
    assert_in("venue search has 'location'",       "location", venues_res)
    assert_equal("venue search location matches",  venues_res["location"], "Bangalore")
    assert_true("at least 1 venue returned",       len(venues_res.get("venues", [])) >= 1)

    top_venue = venues_res["venues"][0]
    assert_in("venue has 'name'",                  "name", top_venue)
    assert_in("venue has 'maps_url'",              "maps_url", top_venue)
    assert_true("maps_url starts with https://",   top_venue.get("maps_url", "").startswith("https://"))


# ============================================================================
# TEST SECTION 3 – Evaluator (live API)
# ============================================================================

def test_evaluator() -> None:
    section("3 · LLM-as-a-Judge Evaluator (live Gemini API)")

    from evaluator import evaluate_plan, format_evaluation_report

    sample_plan = """
    ## Wedding Plan for 80 Guests – ,000 Budget

    ### Budget Breakdown
    - Venue & Catering: ,000 (45%)
    - Photography: ,400 (12%)
    - Decor & Florals: ,400 (12%)
    - Attire & Beauty: ,600 (8%)
    - Entertainment: ,600 (8%)
    - Contingency Buffer: ,000 (15%)

    ### Timeline
    - 12 months out: Book venue and photographer
    - 6 months out: Confirm caterer and florist
    - 1 month out: Final headcount and seating plan
    - Day-of: 6am makeup, 2pm ceremony, 5pm reception

    ### Vendor Checklist
    - Photographer, Caterer, Florist, DJ, Officiant

    We are so excited for your big day! Everything will be perfect. 🌸
    """

    info("Calling evaluate_plan() with a sample wedding plan…")
    result = evaluate_plan(sample_plan)

    assert_true("evaluator returned a dict",        isinstance(result, dict))
    assert_true("no error in evaluation",           "error" not in result,
                result.get("error", ""))
    assert_in("result has 'scores'",               "scores",       result)
    assert_in("result has 'feedback'",             "feedback",     result)
    assert_in("result has 'overall_score'",        "overall_score", result)
    assert_in("result has 'pass_fail'",            "pass_fail",    result)
    assert_in("result has 'summary'",              "summary",      result)

    scores = result.get("scores", {})
    for dim in ("event_type_alignment", "budget_correctness",
                "timeline_feasibility", "tone_and_empathy"):
        s = scores.get(dim)
        assert_true(f"  score '{dim}' in range 1–5",
                    isinstance(s, (int, float)) and 1 <= s <= 5,
                    str(s))

    verdict = result.get("pass_fail", "")
    assert_true("verdict is PASS or FAIL",          verdict in ("PASS", "FAIL"), verdict)

    info("Evaluator report formatted output:")
    report = format_evaluation_report(result)
    assert_true("report is a non-empty string",    isinstance(report, str) and len(report) > 50)
    # Print a truncated preview (strip Rich markup for readability)
    import re
    clean = re.sub(r"\[.*?\]", "", report)
    for line in clean.split("\n")[:12]:
        print(f"    {line}")


# ============================================================================
# TEST SECTION 4 – Full ADK Agent Round-trip (live API)
# ============================================================================

async def _run_agent_turn(user_message: str) -> str:
    """Run one turn through the ADK Runner and return the response text."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from agent import root_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="planning-puppet-test",
        user_id="test-user",
        state={},
    )
    runner = Runner(
        app_name="planning-puppet-test",
        agent=root_agent,
        session_service=session_service,
    )
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)],
    )
    response_text = ""
    async for event in runner.run_async(
        user_id="test-user",
        session_id=session.id,
        new_message=content,
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    response_text = part.text
    return response_text


def test_agent_roundtrip() -> None:
    section("4 · ADK Agent Full Round-trip (live Gemini API)")

    info("Sending a compact birthday planning request to the agent…")
    prompt = (
        "Plan a small 30th birthday dinner for 15 guests with a ,000 budget. "
        "We like an elegant aesthetic. Event date: 2027-03-20."
    )

    response_text = asyncio.run(_run_agent_turn(prompt))

    assert_true("agent returned a non-empty response",
                len(response_text) > 100,
                f"response length = {len(response_text)}")

    # Check that budget tool was used (should mention dollar amounts)
    assert_true("response mentions budget/dollar",
                "$" in response_text or "budget" in response_text.lower(),
                response_text[:80])

    # Check that a planning-related keyword is present
    keywords = ["vendor", "timeline", "phase", "milestone", "checklist",
                "pinterest", "decor", "birthday", "guests", "dinner"]
    matched = [kw for kw in keywords if kw in response_text.lower()]
    assert_true(f"response contains planning keywords ({matched[:3]})",
                len(matched) >= 2,
                f"matched: {matched}")

    info("Agent response preview (first 300 chars):")
    print(f"\n    {'─'*50}")
    for line in response_text[:300].split("\n"):
        print(f"    {line}")
    print(f"    {'─'*50}\n")


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Planning Puppet backend verification suite."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip all live Gemini API tests (tools-only mode).",
    )
    args = parser.parse_args()

    # Force UTF-8 output on Windows to handle any remaining unicode
    import sys, io
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  [**] Planning Puppet - Backend Test Suite{RESET}")
    print(f"{BOLD}{'='*55}{RESET}")

    api_available = test_environment(offline=args.offline)
    test_tools()

    if api_available:
        try:
            test_evaluator()
        except Exception as exc:
            fail(f"Evaluator test crashed: {exc}")
            global failed
            failed += 1

        try:
            test_agent_roundtrip()
        except Exception as exc:
            fail(f"Agent round-trip test crashed: {exc}")
            failed += 1
    else:
        warn("Skipping live API tests (offline mode).")

    # ── Final summary ────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*55}{RESET}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}  ALL {total} TESTS PASSED [OK]{RESET}")
    else:
        print(f"{RED}{BOLD}  {failed} of {total} TESTS FAILED [X]{RESET}")
        print(f"{GREEN}  {passed} passed{RESET}")
    print(f"{BOLD}{'='*55}{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

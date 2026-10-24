import asyncio
import json
from types import SimpleNamespace

from review_core.finalizer import NO_REVIEW_MESSAGE, RESET_STATE, ReportFinalizer, ReviewReset
from review_core.review_tools import review_security
from review_core.analysis.scoring import (
    FIX_HINTS,
    ReviewReport,
    build_report,
    extra_fixes_from,
    score_checks,
    verdict_for,
)


def check(criterion, check_id, passed=True, applicable=True, reason="because"):
    return {"id": check_id, "criterion": criterion, "passed": passed, "applicable": applicable, "reason": reason}


# ---- scoring ---------------------------------------------------------------- #
def test_score_is_percent_passed_per_criterion_and_mean_overall():
    checks = [
        check("security", "a"), check("security", "b", passed=False),   # 50
        check("scope", "c"),                                            # 100
    ]
    overall, per = score_checks(checks)
    assert per == {"security": 50, "scope": 100} and overall == 75


def test_not_applicable_checks_and_empty_criteria_are_ignored():
    checks = [check("scope", "a"), check("scope", "b", passed=False, applicable=False)]
    overall, per = score_checks(checks)
    assert per == {"scope": 100} and overall == 100
    assert score_checks([]) == (0, {})


def test_verdict_needs_high_score_and_perfect_security():
    assert verdict_for(90, {"security": 100}) == "ready"
    assert verdict_for(85, {"security": 100}) == "ready"
    assert verdict_for(84, {"security": 100}) == "needs_changes"
    assert verdict_for(95, {"security": 50}) == "needs_changes"
    assert verdict_for(90, {"scope": 100}) == "ready"  # no security checks applicable


def test_every_check_id_has_a_fix_hint(tmp_path, monkeypatch):
    from review_core.analysis import links
    from review_core.analysis.checks import run_deterministic_checks

    monkeypatch.setattr(links, "_fetch_status", lambda url: 200)
    proj = tmp_path / "some-project"
    proj.mkdir()
    (proj / "README.md").write_text("# Demo\n## Overview\nShort.\n")  # a README so every check is emitted
    ids = {c["id"] for c in run_deterministic_checks("some-project")["checks"]}
    assert len(ids) == 16 and ids == set(FIX_HINTS)


# ---- report building -------------------------------------------------------- #
def test_report_failures_and_fixes_come_from_the_checks():
    checks = [check("security", "no_secrets", passed=False, reason="x.py: Possible key"),
              check("scope", "folder_name_ok")]
    report = build_report(checks)
    assert [f.id for f in report.failures] == ["no_secrets"]
    assert report.suggested_fixes == [FIX_HINTS["no_secrets"]]
    assert report.verdict == "needs_changes"


def test_model_extras_are_cleaned_capped_and_deduplicated():
    checks = [check("scope", "folder_name_ok", passed=False)]
    fake_key = "AIza" + "Z" * 35
    extras = [FIX_HINTS["folder_name_ok"], f"Rotate {fake_key} now", "  ", 42, "x" * 1000,
              "a", "b", "c", "d"]
    fixes = build_report(checks, extras).suggested_fixes
    assert fixes[0] == FIX_HINTS["folder_name_ok"] and fixes.count(FIX_HINTS["folder_name_ok"]) == 1
    assert fake_key not in " ".join(fixes) and "[REDACTED]" in " ".join(fixes)
    assert all(len(f) <= 300 for f in fixes)
    assert len(fixes) <= 1 + 5


def test_report_is_repeatable():
    checks = [check("scope", "a"), check("security", "b", passed=False)]
    assert build_report(checks).model_dump() == build_report(checks).model_dump()


def test_extra_fixes_from_dict_json_and_junk():
    assert extra_fixes_from({"suggested_fixes": ["a"]}) == ["a"]
    assert extra_fixes_from('{"suggested_fixes": ["b"]}') == ["b"]
    assert extra_fixes_from("not json") == []
    assert extra_fixes_from(None) == []
    assert extra_fixes_from({"suggested_fixes": "oops"}) == []


def test_schema_has_no_free_form_maps():
    assert "additionalProperties" not in json.dumps(ReviewReport.model_json_schema())


# ---- review tools ----------------------------------------------------------- #
def test_review_tool_saves_checks_in_state(tmp_path):
    proj = tmp_path / "my-agent"
    proj.mkdir()
    ctx = SimpleNamespace(state={})
    result = review_security("my-agent", ctx)
    assert result["criterion"] == "security" and result["score"] is not None
    assert ctx.state["checks_security"] == result["checks"]
    assert ctx.state["review_project"] == "my-agent"


def test_review_tool_error_is_saved_for_the_finalizer_and_no_checks_are():
    ctx = SimpleNamespace(state={})
    assert "error" in review_security("does-not-exist", ctx)
    assert ctx.state == {"review_error": "Path not found: does-not-exist."}


# ---- finalizer -------------------------------------------------------------- #
def run_finalizer(state):
    agent = ReportFinalizer(name="report_finalizer")
    ctx = SimpleNamespace(session=SimpleNamespace(state=state), invocation_id="inv1")

    async def collect():
        return [event async for event in agent._run_async_impl(ctx)]

    (event,) = asyncio.run(collect())
    return event


def test_finalizer_scores_from_checks_not_from_the_model():
    state = {
        "checks_security": [check("security", "no_secrets", passed=False, reason="leak")],
        "llm_review": {"overall_score": 100, "verdict": "ready", "suggested_fixes": ["Subjective: nice"]},
    }
    event = run_finalizer(state)
    report = ReviewReport.model_validate_json(event.content.parts[0].text)
    assert report.overall_score == 0 and report.verdict == "needs_changes"
    assert report.suggested_fixes[-1] == "Subjective: nice"
    assert event.actions.state_delta["final_review"]["overall_score"] == 0
    assert event.author == "report_finalizer"


def test_finalizer_survives_missing_or_junk_model_output():
    checks = {"checks_scope": [check("scope", "folder_name_ok")]}
    for llm in (None, "garbage", {"suggested_fixes": 5}):
        report = ReviewReport.model_validate_json(run_finalizer({**checks, "llm_review": llm}).content.parts[0].text)
        assert report.overall_score == 100 and report.verdict == "ready"


def test_finalizer_shows_the_real_error_when_the_review_could_not_start():
    message = "Path not found: readme-reviwer. Did you mean 'agents/readme-reviewer'?"
    event = run_finalizer({"review_error": message})
    assert event.content.parts[0].text == message and event.actions.state_delta == {}


def test_finalizer_asks_for_a_folder_when_nothing_was_reviewed():
    event = run_finalizer({})
    assert event.content.parts[0].text == NO_REVIEW_MESSAGE and event.actions.state_delta == {}


def test_reset_step_clears_every_key_the_finalizer_reads():
    agent = ReviewReset(name="review_reset")
    ctx = SimpleNamespace(invocation_id="inv1")

    async def collect():
        return [e async for e in agent._run_async_impl(ctx)]

    (event,) = asyncio.run(collect())
    assert event.content is None and event.actions.state_delta == RESET_STATE
    # after the reset, the finalizer sees no stale review
    stale = {"checks_security": [check("security", "no_secrets", passed=False)], **RESET_STATE}
    assert run_finalizer(stale).content.parts[0].text == NO_REVIEW_MESSAGE


# ---- schema guard ----------------------------------------------------------- #
def llm_response(text, partial=False):
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]), partial=partial)


def guarded(text, state=None, partial=False):
    from review_core.safety.schema_guard import ensure_valid_review

    ctx = SimpleNamespace(state=state or {})
    result = ensure_valid_review(ctx, llm_response(text, partial))
    return None if result is None else ReviewReport.model_validate_json(result.content.parts[0].text)


VALID = ReviewReport(
    overall_score=70, criterion_scores={"security": 70}, failures=[], suggested_fixes=["x"], verdict="needs_changes"
).model_dump_json()
STATE = {"checks_security": [check("security", "no_secrets", passed=False)]}


def test_valid_json_passes_through():
    assert guarded(VALID).overall_score == 70


def test_json_buried_in_prose_is_extracted():
    assert guarded(f"We need to answer.\n{VALID}\nDone.").suggested_fixes == ["x"]


def test_prose_is_replaced_by_the_deterministic_report():
    report = guarded("**Merged structured review** all good!", STATE)
    assert report.overall_score == 0 and [f.id for f in report.failures] == ["no_secrets"]


def test_out_of_range_json_is_replaced():
    bad = VALID.replace('"overall_score":70', '"overall_score":500')
    assert guarded(bad, STATE).overall_score == 0


def test_nothing_reviewed_gives_an_empty_valid_report():
    report = guarded("whatever")
    assert report.overall_score == 0 and report.failures == [] and report.verdict == "needs_changes"


def test_streaming_chunks_are_left_alone():
    assert guarded("{\"overall_sc", STATE, partial=True) is None


# ---- team wiring ------------------------------------------------------------ #
def test_team_structure():
    from readme_reviewer_team.agent import root_agent

    reset, reviewers, aggregator, finalizer = root_agent.sub_agents
    assert isinstance(reset, ReviewReset)
    assert root_agent.name == "readme_review_team"
    assert [a.name for a in reviewers.sub_agents] == [
        "reproducibility_reviewer", "documentation_reviewer", "security_reviewer", "scope_reviewer"]
    assert {a.output_key for a in reviewers.sub_agents} == {
        "reproducibility_review", "documentation_review", "security_review", "scope_review"}
    assert aggregator.output_schema is ReviewReport and aggregator.output_key == "llm_review"
    assert not aggregator.tools and aggregator.after_model_callback is not None
    assert isinstance(finalizer, ReportFinalizer)


def test_reviewers_have_least_privilege_tools_and_callbacks():
    from readme_reviewer_team.agent import reviewers

    tools = {a.name: {t.__name__ for t in a.tools} for a in reviewers.sub_agents}
    assert tools["security_reviewer"] == {"review_security"}
    assert tools["scope_reviewer"] == {"review_scope"}
    assert tools["documentation_reviewer"] == {"review_documentation", "read_file"}
    assert all(a.before_tool_callback is not None for a in reviewers.sub_agents)

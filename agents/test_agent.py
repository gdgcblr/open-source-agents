import json
from pathlib import Path

from pr_review_agent.diff_parser import parse_diff
from pr_review_agent.github_client import GitHubError, parse_pr_ref
from pr_review_agent.llm import MockProvider
from pr_review_agent.orchestrator import ReviewOrchestrator, decide_verdict
from pr_review_agent.reviewers import QualityReviewer, SecurityReviewer, parse_llm_findings

SAMPLE = (Path(__file__).parent.parent / "examples" / "sample.diff").read_text()


def test_parser_tracks_line_numbers():
    files = {f.path: f for f in parse_diff(SAMPLE)}
    assert set(files) == {"app/db.py", "app/util.py"}
    assert files["app/db.py"].is_new
    # util.py hunk starts at 10: one context line (10), then added lines from 11
    assert files["app/util.py"].added[0][0] == 11


def test_parser_skips_deleted_files():
    diff = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-gone\n"
    assert parse_diff(diff) == []


def test_removed_line_starting_with_dashes_is_not_a_header():
    diff = (
        "diff --git a/a.sql b/a.sql\n--- a/a.sql\n+++ b/a.sql\n"
        "@@ -1,2 +1,2 @@\n--- old comment\n+-- new comment\n"
    )
    f = parse_diff(diff)[0]
    assert f.added == [(1, "-- new comment")]


def test_security_rules_fire():
    titles = {f.title for f in SecurityReviewer().review(parse_diff(SAMPLE))}
    assert "Hardcoded credential" in titles
    assert "Possible SQL injection" in titles
    assert "Dynamic code execution" in titles


def test_quality_rules_fire():
    titles = {f.title for f in QualityReviewer().review(parse_diff(SAMPLE))}
    assert {"Bare except", "Mutable default argument", "No tests in this PR"} <= titles


def test_placeholder_secret_not_flagged():
    diff = ('diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -0,0 +1,1 @@\n'
            '+API_KEY = "your-api-key-here"\n')
    assert any(f.source == "security:SECRET" for f in SecurityReviewer().review(parse_diff(diff)))


def test_end_to_end_with_mock_provider():
    result = ReviewOrchestrator(MockProvider()).run(SAMPLE)
    assert result.verdict == "REQUEST_CHANGES"
    assert result.counts()["high"] >= 3
    sevs = ["critical", "high", "medium", "low", "info"]
    ranks = [sevs.index(f.severity) for f in result.findings]
    assert ranks == sorted(ranks)
    json.dumps(result.to_dict())  # must be serialisable


def test_verdicts():
    from pr_review_agent.models import Finding

    def mk(sev):
        return Finding("a.py", 1, sev, "quality", "t", "d")

    assert decide_verdict([]) == "APPROVE"
    assert decide_verdict([mk("low")]) == "APPROVE"
    assert decide_verdict([mk("medium")]) == "COMMENT"
    assert decide_verdict([mk("medium"), mk("high")]) == "REQUEST_CHANGES"


def test_llm_output_is_validated():
    f = parse_diff(SAMPLE)[0]
    raw = '```json\n[{"line": 9999, "severity": "BOGUS", "title": "t", "detail": "d"}, {"nope": 1}]\n```'
    out = parse_llm_findings(raw, f, "llm:test")
    assert out == []  # invalid line rejected, not silently reassignedd


def test_garbage_llm_output_is_ignored():
    f = parse_diff(SAMPLE)[0]
    assert parse_llm_findings("I cannot help with that", f, "x") == []


def test_pr_ref():
    assert parse_pr_ref("octo/repo#12") == ("octo", "repo", 12)
    try:
        parse_pr_ref("nonsense")
    except GitHubError:
        pass
    else:
        raise AssertionError("expected GitHubError")

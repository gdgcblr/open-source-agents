from datetime import datetime, timezone
from pathlib import Path

import pytest

from slop_detector.github_client import parse_pr_ref, pull_request_from_patch
from slop_detector.heuristics import added_lines, run_heuristics
from slop_detector.models import ChangedFile, LlmVerdict, PullRequest, Verdict
from slop_detector.models import LlmFinding
from slop_detector.report import combine, evidence_in_pr, to_markdown

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def load(name: str) -> PullRequest:
    return PullRequest.model_validate_json((FIXTURES / name).read_text())


def ids(pr: PullRequest) -> set[str]:
    return {s.id for s in run_heuristics(pr, NOW).signals}


def test_slop_fixture_is_flagged():
    report = run_heuristics(load("slop_pr.json"), NOW)
    assert report.score >= 60
    assert {
        "assistant-leakage", "llm-phrasing", "placeholder-code", "restating-comments", "undeclared-imports",
        "ai-artifact-files", "unverified-claims", "emoji-headings", "whitespace-churn", "pr-spray", "new-account",
    } <= {s.id for s in report.signals}


def test_clean_fixture_passes():
    report = run_heuristics(load("clean_pr.json"), NOW)
    assert report.score < 20, [s.id for s in report.signals]


def test_declared_and_local_imports_are_not_flagged():
    pr = PullRequest(
        files=[ChangedFile(filename="app/main.py", patch="@@ -0,0 +1,4 @@\n+import requests\n+import yaml\n+from utils import x\n+import json")],
        manifests={"requirements.txt": "requests==2.32\nPyYAML>=6\n"},
        local_modules=["app", "utils"],
    )
    assert "undeclared-imports" not in ids(pr)


def test_hallucinated_import_is_flagged():
    pr = PullRequest(
        files=[ChangedFile(filename="app/main.py", patch="@@ -0,0 +1,1 @@\n+import fastjsonschema")],
        manifests={"requirements.txt": "requests\n"},
    )
    assert "undeclared-imports" in ids(pr)


def test_import_check_skipped_without_manifest():
    pr = PullRequest(files=[ChangedFile(filename="a.py", patch="@@ -0,0 +1,1 @@\n+import whatever")])
    assert "undeclared-imports" not in ids(pr)


def test_placeholders_in_env_example_and_docs_are_ignored():
    pr = PullRequest(files=[
        ChangedFile(filename=".env.example", patch="@@ -0,0 +1 @@\n+API_KEY=your_api_key_here"),
        ChangedFile(filename="README.md", patch="@@ -0,0 +1 @@\n+Set `your_api_key` in .env. TODO: implement caching"),
    ])
    assert "placeholder-code" not in ids(pr)


def test_ai_disclosure_alone_is_not_penalized():
    pr = PullRequest(
        title="Fix off-by-one in pagination",
        body="Page 2 repeated the last item of page 1. Written with help from an AI assistant; I verified with the new test.",
        commit_messages=["Fix off-by-one in paginate()\n\nCo-Authored-By: Some Assistant <noreply@example.com>"],
        files=[ChangedFile(filename="src/page.py", additions=1, deletions=1, patch="@@ -3 +3 @@\n-    start = page * size + 1\n+    start = page * size")],
    )
    assert run_heuristics(pr, NOW).score == 0


def test_added_lines_tracks_new_file_line_numbers():
    f = ChangedFile(filename="x.py", patch="@@ -10,3 +10,4 @@\n ctx\n-old\n+new1\n+new2\n ctx")
    assert added_lines(f) == [(11, "new1"), (12, "new2")]


def test_patch_parser_reads_git_diff():
    diff = (FIXTURES / "sample.diff").read_text()
    pr = pull_request_from_patch(diff, title="t")
    assert [f.filename for f in pr.files] == ["src/calc.py", "NOTES.md"]
    assert pr.files[1].status == "added"
    assert pr.files[0].additions == 3 and pr.files[0].deletions == 1


@pytest.mark.parametrize("ref,expected", [
    ("octo/repo#12", ("octo/repo", 12)),
    ("https://github.com/octo/my.repo/pull/345", ("octo/my.repo", 345)),
    ("https://github.com/octo/repo/pull/7/files", ("octo/repo", 7)),
])
def test_parse_pr_ref(ref, expected):
    assert parse_pr_ref(ref) == expected


def test_combine_weights_llm_over_heuristics():
    pr = load("clean_pr.json")
    heur = run_heuristics(pr, NOW)
    llm = LlmVerdict(slop_score=80, verdict=Verdict.LIKELY_SLOP, summary="s")
    r = combine(pr, heur, llm, threshold=60)
    assert r.score == round(0.65 * 80 + 0.35 * heur.score)
    md = to_markdown(r)
    assert "PR Slop Check" in md and "Heuristic signals" in md


def test_bots_skip_author_and_template_checks():
    pr = load("clean_pr.json")
    pr.author.login, pr.author.recent_pr_count, pr.author.recent_pr_repo_count = "dependabot[bot]", 10_000, 90
    pr.body = "Bumps requests. " * 200
    assert run_heuristics(pr, NOW).score == 0


def test_evidence_must_occur_in_pr():
    pr = load("slop_pr.json")
    assert evidence_in_pr(pr, "import fastjsonschema")
    assert evidence_in_pr(pr, "  `I hope this HELPS`  ")  # whitespace, backticks, case are ignored
    assert not evidence_in_pr(pr, "user_service/api.py")  # a bare file name is not evidence
    assert not evidence_in_pr(pr, "import totally_made_up_module")
    assert not evidence_in_pr(pr, "")


def test_unverified_evidence_is_hidden_in_report():
    pr = load("slop_pr.json")
    llm = LlmVerdict(slop_score=70, verdict=Verdict.LIKELY_SLOP, summary="s", findings=[
        LlmFinding(claim="real", file="user_service/api.py", evidence="import fastjsonschema", severity="high"),
        LlmFinding(claim="fake", file="user_service/api.py", evidence="user_service/api.py", severity="low"),
    ])
    md = to_markdown(combine(pr, run_heuristics(pr, NOW), llm, threshold=60))
    assert "> `import fastjsonschema`" in md
    assert "> `user_service/api.py`" not in md


def test_pseudo_findings_without_severity_are_dropped():
    pr = load("clean_pr.json")
    llm = LlmVerdict(slop_score=10, verdict=Verdict.LOOKS_GOOD, summary="s", findings=[
        LlmFinding(claim="No significant issues were found.", evidence="", severity="None"),
    ])
    md = to_markdown(combine(pr, run_heuristics(pr, NOW), llm, threshold=60))
    assert "### Findings" not in md


def test_unsupported_llm_score_is_down_weighted():
    pr = load("clean_pr.json")
    heur = run_heuristics(pr, NOW)
    unsupported = LlmVerdict(slop_score=85, verdict=Verdict.LIKELY_SLOP, summary="s", findings=[
        LlmFinding(claim="huge lockfile change", file="uv.lock", evidence="uv.lock", severity="high"),
    ])
    r = combine(pr, heur, unsupported, threshold=60)
    assert r.score == round(0.3 * 85 + 0.7 * heur.score)
    assert r.verdict == Verdict.LOOKS_GOOD
    assert "down-weighted" in to_markdown(r)

    supported = unsupported.model_copy(update={"findings": [
        LlmFinding(claim="c", file="user_service/api.py", evidence="if resp.status_code == 404:", severity="high"),
    ]})
    assert combine(pr, heur, supported, threshold=60).score == round(0.65 * 85 + 0.35 * heur.score)

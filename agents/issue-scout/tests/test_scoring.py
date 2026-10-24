from conftest import ts
from issue_scout.models import Candidate, IssueSignals, Mention, Profile, PullRef, RepoHealth
from issue_scout.scoring import estimate_effort, evaluate


def make(signals=None, health=None, **overrides):
    fields = dict(
        repo="o/r",
        number=1,
        title="Fix crash",
        url="https://github.com/o/r/issues/1",
        labels=["good first issue"],
        created_at=ts(30),
        updated_at=ts(3),
        comments=2,
        body="Detailed steps to reproduce. " * 20,
    )
    fields.update(overrides)
    candidate = Candidate(**fields)
    candidate.signals = signals or IssueSignals()
    candidate.repo_health = health or RepoHealth("o/r", stars=900, outside_merged=6, outside_closed_unmerged=2, median_merge_days=3)
    return candidate


PROFILE = Profile(languages=["python"], hours=3)


def test_clean_issue_is_ready(now):
    result = evaluate(make(), PROFILE, now)
    assert result.verdict == "ready"
    assert result.flags == []
    assert result.score >= 80
    assert any("merges 75% of recent outside PRs" in r for r in result.reasons)


def test_open_pr_makes_it_a_dead_end(now):
    signals = IssueSignals(pulls=[PullRef(5, "u", "t", "open")])
    result = evaluate(make(signals), PROFILE, now)
    assert result.verdict == "skip"
    assert "open-pr" in result.flags


def test_assigned_is_skip(now):
    result = evaluate(make(IssueSignals(assignees=["alice"])), PROFILE, now)
    assert result.verdict == "skip"


def test_maintainer_says_fixed_is_skip_but_contributor_is_caution(now):
    maint = IssueSignals(resolved_hints=[Mention("m", ts(1), "u", "fixed in #2", True)])
    visitor = IssueSignals(resolved_hints=[Mention("v", ts(1), "u", "already exists", False)])
    assert evaluate(make(maint), PROFILE, now).verdict == "skip"
    result = evaluate(make(visitor), PROFILE, now)
    assert result.verdict == "caution"
    assert "possibly-resolved" in result.flags


def test_open_policy_softens_claim_penalty(now):
    claim = [Mention("x", ts(2), "u", "can I work on this")]
    strict = evaluate(make(IssueSignals(active_claims=list(claim))), PROFILE, now)
    relaxed = evaluate(
        make(IssueSignals(active_claims=list(claim), open_policy=Mention("m", ts(1), "u", "just open a PR", True))),
        PROFILE,
        now,
    )
    assert strict.verdict == relaxed.verdict == "caution"
    assert relaxed.score - strict.score == 20


def test_tiny_outside_sample_is_not_judged(now):
    health = RepoHealth("o/r", outside_merged=1, outside_closed_unmerged=0, median_merge_days=0.1)
    result = evaluate(make(health=health), PROFILE, now)
    assert not any("merge" in r for r in result.reasons)


def test_core_team_only_repo_is_penalised(now):
    health = RepoHealth("o/r", closed_sample=30)
    result = evaluate(make(health=health), PROFILE, now)
    assert any("core team" in r for r in result.reasons)


def test_old_and_large_issue_gets_cautions(now):
    candidate = make(created_at=ts(900), labels=["enhancement"], body="- [ ] a\n- [ ] b\n- [ ] c\n- [ ] d\n" * 3)
    result = evaluate(candidate, PROFILE, now)
    assert result.effort == "large"
    assert {"old-issue", "may-exceed-time"} <= set(result.flags)
    assert result.verdict == "caution"


def test_rfc_and_urgent_labels_are_penalised(now):
    plain = evaluate(make(), PROFILE, now)
    rfc = evaluate(make(labels=["good first issue", "RFC", "high priority"]), PROFILE, now)
    assert "needs-decision" in rfc.flags and rfc.verdict == "caution"
    assert plain.score - rfc.score == 20


def test_effort_estimate_from_labels():
    assert estimate_effort(make(labels=["documentation"], body="typo")) == "small"
    assert estimate_effort(make(labels=["bug"], body="x")) == "medium"
    assert estimate_effort(make(labels=["feature"], body="x" * 3000)) == "large"


def test_score_is_clamped(now):
    signals = IssueSignals(
        active_claims=[Mention("x", ts(1), "u", "mine")],
        pulls=[PullRef(1, "u", "t", "closed")],
        resolved_hints=[Mention("v", ts(1), "u", "already done")],
    )
    candidate = make(signals, RepoHealth("o/r", outside_closed_unmerged=9), created_at=ts(2000), updated_at=ts(400), comments=40, body="")
    assert evaluate(candidate, PROFILE, now).score == 0

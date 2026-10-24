import pytest

from conftest import comment, cross_ref, pull, repo_payload
from issue_scout.signals import analyze_timeline, detect_claim, detect_open_policy, detect_resolved, repo_health


@pytest.mark.parametrize(
    "text",
    [
        "Can I work on this?",
        "Hi! I'd like to work on this issue.",
        "I would love to take this one",
        "I'll take this",
        "I am working on it",
        "Please assign this to me",
        "I'm interested in working on this",
        "/assign",
    ],
)
def test_detect_claim_positive(text):
    assert detect_claim(text)


@pytest.mark.parametrize(
    "text",
    [
        "This is still broken on 2.1",
        "Thanks for the report!",
        "> Can I work on this?\nPlease just open a PR.",  # quoted claim is not a new claim
        "The assignment operator is wrong here",
    ],
)
def test_detect_claim_negative(text):
    assert detect_claim(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "This already exists on master",
        "Fixed in #1234",
        "resolved by https://github.com/o/r/pull/9",
        "Duplicate of #77",
        "I think this can be closed now",
        "This is no longer reproducible",
    ],
)
def test_detect_resolved_positive(text):
    assert detect_resolved(text)


def test_detect_resolved_negative():
    assert detect_resolved("I tried to fix it but the tests fail") is None


def test_detect_open_policy():
    assert detect_open_policy("We don't assign tickets, you can just pick things up")
    assert detect_open_policy("No need to ask, just open a PR!")
    assert detect_open_policy("Looks good to me") is None


def test_analyze_timeline_claims_prs_and_policy(now):
    timeline = [
        comment("Can I work on this?", author="old", days_ago=200),
        comment("I'd like to work on this", author="new", days_ago=3),
        comment("We don't assign issues, feel free to open a PR", author="maint", role="MEMBER", days_ago=2),
        comment("Can I work on this?", author="dependabot[bot]", bot=True),
        cross_ref(10, state="open"),
        cross_ref(10, state="open"),  # duplicate reference
        cross_ref(11, state="closed", merged=True),
        cross_ref(12, state="closed"),
        cross_ref(13, state="open", repo="other/fork"),  # PR in another repo
        cross_ref(14, state="open", is_pr=False),  # a mere issue mention
    ]
    signals = analyze_timeline(timeline, "o/r", [], now)

    assert [m.author for m in signals.active_claims] == ["new"]
    assert [m.author for m in signals.stale_claims] == ["old"]
    assert signals.open_policy is not None and signals.open_policy.author == "maint"
    assert signals.maintainer_comments == 1
    assert [(p.number, p.state) for p in signals.pulls] == [(10, "open"), (11, "merged"), (12, "closed")]


def test_resolved_hint_records_maintainer_role(now):
    timeline = [
        comment("Fixed in #99", author="maint", role="OWNER"),
        comment("this already exists", author="visitor"),
    ]
    hints = analyze_timeline(timeline, "o/r", [], now).resolved_hints
    assert [(h.author, h.is_maintainer) for h in hints] == [("maint", True), ("visitor", False)]


def test_repo_health_counts_only_outside_humans():
    pulls = [
        pull(role="CONTRIBUTOR", merged_days=2),
        pull(role="FIRST_TIME_CONTRIBUTOR", merged_days=4),
        pull(role="NONE"),  # closed without merge
        pull(role="MEMBER", merged_days=1),  # core team, ignored
        pull(role="CONTRIBUTOR", merged_days=1, bot=True),  # bot, ignored
    ]
    health = repo_health(repo_payload(), pulls)
    assert health.outside_merged == 2
    assert health.outside_closed_unmerged == 1
    assert health.median_merge_days == 3.0
    assert health.closed_sample == 5
    assert round(health.outside_merge_ratio, 2) == 0.67

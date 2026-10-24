"""Offline checks of the real-PR manifest. The eval itself needs network: python -m evals.run_real_prs_eval"""

import re

from evals.run_real_prs_eval import PinnedPR, compare, load_manifest
from prcheck.registry import all_checks

VALID_STATUSES = {"fail", "warn", "info"}


def test_manifest_is_well_formed():
    meta, prs = load_manifest()
    assert re.fullmatch(r"[0-9a-f]{40}", meta["base_sha"])
    assert meta["repo_url"].startswith("https://github.com/")
    known_ids = {spec.id for spec in all_checks()}
    seen = set()
    for pr in prs:
        assert re.fullmatch(r"[0-9a-f]{40}", pr.sha), pr.number
        assert (pr.number, pr.folder) not in seen, f"duplicate entry for #{pr.number} {pr.folder}"
        seen.add((pr.number, pr.folder))
        assert set(pr.expect) <= known_ids, pr.number
        assert set(pr.expect.values()) <= VALID_STATUSES, pr.number
        # ready must agree with expect: not ready exactly when some check is expected to fail
        assert pr.ready == ("fail" not in pr.expect.values()), pr.number
        assert pr.reviewed and pr.why, f"#{pr.number} needs a review date and a reason"


def test_manifest_includes_this_tools_own_pr():
    _, prs = load_manifest()
    assert any(pr.folder == "tools/pr-readiness-checker" and pr.ready for pr in prs)


def test_compare_reports_every_kind_of_mismatch():
    pr = PinnedPR(number=1, sha="0" * 40, folder="tools/x", expect={"D2": "fail", "M1": "fail"},
                  ready=False, reviewed="2026-10-24", why="test")
    problems = compare(pr, {"D2": "warn", "X2": "fail", "S1": "pass", "G1": "crash"})
    assert "D2 expected fail, got warn" in problems
    assert "X2 unexpectedly fail" in problems
    assert "G1 crashed" in problems
    assert "M1 expected fail but did not run" in problems
    assert compare(pr, {"D2": "fail", "M1": "fail", "S1": "pass", "G1": "skip"}) == []

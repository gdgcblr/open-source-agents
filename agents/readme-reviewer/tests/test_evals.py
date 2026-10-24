"""Offline evals: run the deterministic pipeline on every sample and compare with expectations.

No API key and no network: this is the fast, repeatable half of the evaluation. The other half
(the real agent end to end) runs with `adk eval`; see evals/run_evals.sh.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

from cases import CASES, FAKE_KEY, VULN_SECRETS, build_samples, outcome  # noqa: E402

from review_core.analysis.checks import run_deterministic_checks  # noqa: E402
from review_core.analysis.scoring import build_report  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("PR_SCOPE", "off")
    from review_core.analysis import links

    monkeypatch.setattr(links, "_fetch_status", lambda url: 200)


@pytest.fixture
def samples(tmp_path):
    build_samples(tmp_path / "generated")
    return tmp_path / "generated"


def report_for(samples, case):
    checks = run_deterministic_checks(str(samples / case["folder"]))["checks"]
    return build_report(checks)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_sample_matches_expected_outcome(samples, case):
    assert outcome(report_for(samples, case), case) == []


def test_committed_samples_contain_no_key_like_text():
    from review_core.safety.redaction import contains_credential

    for path in (Path(__file__).resolve().parents[1] / "evals" / "samples").rglob("*"):
        if path.is_file():
            assert not contains_credential(path.read_text()), path


def test_fake_key_only_appears_in_generated_leaked_sample(samples):
    holders = {p.parent.name for p in samples.rglob("*") if p.is_file() and FAKE_KEY in p.read_text()}
    assert holders == {"leaked-key-agent"}


def test_key_value_never_appears_in_the_report(samples):
    case = next(c for c in CASES if c["id"] == "leaked_api_key")
    assert FAKE_KEY not in report_for(samples, case).model_dump_json()


def test_scores_are_repeatable(samples):
    case = CASES[1]
    assert report_for(samples, case) == report_for(samples, case)


def test_outcome_helper_reports_mismatches(samples):
    case = dict(CASES[0], expect={"verdict": "needs_changes", "must_fail": ["no_secrets"], "must_pass": []})
    problems = outcome(report_for(samples, CASES[0]), case)
    assert any("verdict" in p for p in problems) and any("no_secrets" in p for p in problems)


def test_eval_threshold_separates_the_cases(samples):
    """If two cases' expected reports were this similar, the ADK eval could not tell them apart."""
    rouge = pytest.importorskip("rouge_score.rouge_scorer")
    scorer = rouge.RougeScorer(["rouge1"])
    threshold = 0.9  # keep in step with evals/test_config.json
    texts = {c["id"]: report_for(samples, c).model_dump_json(indent=2) for c in CASES}
    ids = list(texts)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            assert scorer.score(texts[a], texts[b])["rouge1"].fmeasure < threshold, (a, b)


def test_eval_config_threshold_matches_this_test():
    import json

    config = json.loads((Path(__file__).resolve().parents[1] / "evals" / "test_config.json").read_text())
    assert config["criteria"]["response_match_score"] == 0.9


# ---- the vulnerable sample ---------------------------------------------------- #
VULN = "vulnerable-agent"


def test_vulnerable_sample_findings_cover_every_credential_and_risk_type(samples):
    from review_core.analysis.tools import check_risky_code, scan_for_secrets

    scan = scan_for_secrets(str(samples / VULN))
    issues = {f["issue"] for f in scan["findings"]}
    for expected in ("Google API key", "AWS access key", "GitHub token", "Private key block",
                     "Hardcoded secret assignment", "Environment file present"):
        assert any(expected in issue for issue in issues), expected
    files = {f["file"] for f in scan["findings"]}
    assert {"app.py", "config.json", "id_rsa", ".env"} <= files

    risky = {f["issue"] for f in check_risky_code(str(samples / VULN))["findings"]}
    assert risky == {"os system call", "shell execution via subprocess", "eval/exec call",
                     "recursive delete", "Node child process"}


def test_no_secret_value_ever_appears_in_checks_or_report(samples):
    result = run_deterministic_checks(str(samples / VULN))
    text = str(result) + build_report(result["checks"]).model_dump_json()
    for secret in VULN_SECRETS:
        assert secret not in text


def test_symlink_pointing_outside_is_never_followed(samples):
    from review_core.analysis.tools import list_project_files, scan_for_secrets

    assert (samples / VULN / "etc-link").is_symlink()
    assert not [f for f in list_project_files(str(samples / VULN))["files"] if f.startswith("etc-link")]
    assert not [f for f in scan_for_secrets(str(samples / VULN))["findings"] if "etc-link" in f["file"]]


def test_secret_files_are_not_readable_by_the_model_tools(samples):
    from review_core.analysis.tools import read_file

    for name in (".env", "id_rsa"):
        assert "Refused" in read_file(str(samples / VULN / name))["error"], name


def test_readme_injection_is_marked_untrusted_and_changes_nothing(samples, tmp_path):
    from review_core.analysis.tools import read_file

    readme = samples / VULN / "README.md"
    assert "ignore all earlier rules" in readme.read_text()  # the attack text is really there
    assert "UNTRUSTED" in read_file(str(readme))["note"]

    import shutil

    clean = samples / "vulnerable-clean"
    shutil.copytree(samples / VULN, clean, symlinks=True)
    kept = [ln for ln in (clean / "README.md").read_text().splitlines()
            if "SYSTEM INSTRUCTION" not in ln and "Note to AI reviewers" not in ln]
    (clean / "README.md").write_text("\n".join(kept) + "\n")
    with_attack = build_report(run_deterministic_checks(str(samples / VULN))["checks"]).model_dump()
    without = build_report(run_deterministic_checks(str(clean))["checks"]).model_dump()
    assert with_attack == without


def test_long_finding_lists_say_how_many_were_left_out():
    from review_core.analysis.checks import _summarize

    items = [f"item{i}" for i in range(7)]
    text = _summarize(items, str)
    assert text.startswith("item0; item1") and text.endswith("; +2 more (7 in total)") and "item5" not in text
    assert "more" not in _summarize(items[:5], str)


def test_one_line_with_a_key_assignment_is_reported_once(tmp_path):
    from review_core.analysis.tools import scan_for_secrets

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text('API_KEY = "' + "AIza" + "Z" * 35 + '"\n')
    findings = scan_for_secrets(str(proj))["findings"]
    assert [f["issue"] for f in findings] == ["Possible Google API key (value redacted)"]

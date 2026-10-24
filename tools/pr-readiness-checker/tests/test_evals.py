"""The deterministic eval suites double as regression tests."""

from evals import run_checks_eval, run_secrets_eval


def test_every_labelled_case_matches():
    results, _ = run_checks_eval.evaluate()
    failures = {r.name: r.mismatches for r in results if not r.ok}
    assert not failures


def test_secret_scanner_meets_targets():
    for seed in (7, 99):
        result = run_secrets_eval.evaluate(per_type=100, seed=seed)
        assert run_secrets_eval.passes(result), result

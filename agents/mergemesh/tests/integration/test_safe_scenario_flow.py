"""Integration tests for the safe_optional_field compatible scenario."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import load_settings
from services.analyze_service import run_scenario_analysis


def test_safe_optional_field_passes_all_checks_with_zero_critical_findings(
    fixtures_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a compatible optional field addition passes isolated and combined checks
    and produces no false critical or high alerts.
    """
    monkeypatch.setenv("MERGEMESH_AI_MODE", "local")
    settings = load_settings()

    report = run_scenario_analysis(
        scenario_id="safe_optional_field",
        settings=settings,
        fixtures_root=fixtures_root,
        include_ai=True,
        run_post_fix=False,
    )

    assert report.scenario_id == "safe_optional_field"
    assert report.overall_status == "COMPATIBLE_PASS"
    assert report.finding_list == []

    for tr in report.test_results:
        assert tr.status == "PASS", f"Expected {tr.test_id} to PASS, got {tr.status}: {tr.stderr}"
        assert tr.exit_code == 0

    assert "display_name" in report.contract_comparison.added_fields
    assert report.contract_comparison.removed_fields == []
    assert report.contract_comparison.is_breaking_candidate is False

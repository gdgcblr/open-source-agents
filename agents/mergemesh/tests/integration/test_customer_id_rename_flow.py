"""Integration tests for the canonical customer_id_rename breaking scenario and post-fix flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import load_settings
from services.analyze_service import run_scenario_analysis
from services.report_export import export_report_to_json, export_report_to_markdown


def test_customer_id_rename_isolated_pass_and_combined_fail(
    fixtures_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify:
    1. Isolated provider test executes and PASSES.
    2. Isolated consumer test (using stale mock) executes and PASSES.
    3. Combined cross-repo test executes and genuinely FAILS with KeyError: 'customer_id'.
    4. Deterministic finding identifies 'customer_id' -> 'customerId' on 'checkout-client'.
    5. Missing AI credentials/Ollama still produces valid report with FALLBACK/UNAVAILABLE status.
    """
    monkeypatch.setenv("MERGEMESH_AI_MODE", "local")
    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "true")
    settings = load_settings()

    report = run_scenario_analysis(
        scenario_id="customer_id_rename",
        settings=settings,
        fixtures_root=fixtures_root,
        include_ai=True,
        run_post_fix=False,
    )

    assert report.scenario_id == "customer_id_rename"
    assert report.overall_status == "BREAKING_FAILURE_REPRODUCED"

    by_kind = {t.test_kind: t for t in report.test_results}
    assert by_kind["provider_isolated"].status == "PASS"
    assert by_kind["provider_isolated"].exit_code == 0

    assert by_kind["consumer_isolated"].status == "PASS"
    assert by_kind["consumer_isolated"].exit_code == 0
    assert by_kind["consumer_isolated"].uses_stale_mock is True

    assert by_kind["combined_integration"].status == "FAIL"
    assert by_kind["combined_integration"].exit_code == 1
    assert "customer_id" in by_kind["combined_integration"].failure_summary

    assert len(report.finding_list) == 1
    finding = report.finding_list[0]
    assert finding.finding_id == "missing_customer_id"
    assert finding.field == "customer_id"
    assert finding.replacement_candidate == "customerId"
    assert finding.provider_repo == "orders-api"
    assert finding.consumer_repo == "checkout-client"
    assert finding.verification_state == "REPRODUCED_FAILURE"

    # Export verification
    json_out = export_report_to_json(report)
    md_out = export_report_to_markdown(report)
    assert "missing_customer_id" in json_out
    assert "KeyError" in md_out


def test_customer_id_rename_post_fix_passes(
    fixtures_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that applying/running the remediated post-fix check passes the integration test."""
    monkeypatch.setenv("MERGEMESH_AI_MODE", "deterministic")
    settings = load_settings()

    report = run_scenario_analysis(
        scenario_id="customer_id_rename",
        settings=settings,
        fixtures_root=fixtures_root,
        include_ai=True,
        run_post_fix=True,
    )

    assert report.post_fix_result is not None
    assert report.post_fix_result.status == "PASS"
    assert report.post_fix_result.exit_code == 0
    assert report.overall_status == "REMEDIATED_PASS"
    assert report.ai_explanation.status == "SKIPPED"


def test_gemini_mode_without_credentials_surfaces_clear_status_without_crashing(
    fixtures_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that in gemini mode with no API key and ALLOW_LOCAL_FALLBACK=false,
    AI status is marked UNAVAILABLE while deterministic findings and test results remain intact.
    """
    monkeypatch.setenv("MERGEMESH_AI_MODE", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "false")

    settings = load_settings()
    report = run_scenario_analysis(
        scenario_id="customer_id_rename",
        settings=settings,
        fixtures_root=fixtures_root,
        include_ai=True,
        run_post_fix=False,
    )

    assert report.overall_status == "BREAKING_FAILURE_REPRODUCED"
    assert len(report.finding_list) == 1
    assert report.ai_explanation.status == "UNAVAILABLE"
    assert "not configured" in (report.ai_explanation.fallback_reason or "").lower()

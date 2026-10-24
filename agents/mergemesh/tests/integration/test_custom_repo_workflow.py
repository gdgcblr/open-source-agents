"""Automated tests for reusable local Git repository analysis (independent of bundled fixtures)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from analysis.contract_extractor import ContractAnalysisError
from analysis.git_inspector import RepoInspectionError
from config.settings import load_settings
from services.analyze_service import (
    CustomRepoAnalysisRequest,
    run_custom_repo_analysis,
)


def _git(cwd: Path, *args: str) -> None:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    assert res.returncode == 0


def _init_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(repo_dir, "init")
    _git(repo_dir, "config", "user.email", "test@mergemesh.local")
    _git(repo_dir, "config", "user.name", "MergeMesh Test")


def test_custom_git_repos_breaking_rename_static_and_reproduced_and_postfix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create two temporary Git repositories ('billing-service' and 'invoice-worker')
    with a custom directory layout and field rename ('account_uuid' -> 'accountUuid').
    Verify:
    1. Without test approval, static analysis detects INFERRED_RISK and does NOT execute user tests.
    2. With explicit test approval, the combined test fails with KeyError: 'account_uuid' -> REPRODUCED_FAILURE.
    3. Post-fix verification executes the remediated test and passes -> REMEDIATED_PASS.
    """
    monkeypatch.setenv("MERGEMESH_AI_MODE", "deterministic")
    settings = load_settings()

    provider_repo = tmp_path / "billing-service"
    consumer_repo = tmp_path / "invoice-worker"
    _init_git_repo(provider_repo)
    _init_git_repo(consumer_repo)

    # Provider commit 1 (base): uses 'account_uuid'
    schema_dir = provider_repo / "schemas" / "v1"
    schema_dir.mkdir(parents=True)
    (schema_dir / "account.json").write_text(
        json.dumps({"account_uuid": "acc_777", "tier": "enterprise"}),
        encoding="utf-8",
    )
    (provider_repo / "billing_api.py").write_text(
        'def get_billing_account() -> dict:\n    return {"account_uuid": "acc_777", "tier": "enterprise"}\n',
        encoding="utf-8",
    )
    _git(provider_repo, "add", ".")
    _git(provider_repo, "commit", "-m", "Initial v1 billing contract")

    # Provider commit 2 (HEAD): renames 'account_uuid' -> 'accountUuid'
    (schema_dir / "account.json").write_text(
        json.dumps({"accountUuid": "acc_777", "tier": "enterprise"}),
        encoding="utf-8",
    )
    (provider_repo / "billing_api.py").write_text(
        'def get_billing_account() -> dict:\n    return {"accountUuid": "acc_777", "tier": "enterprise"}\n',
        encoding="utf-8",
    )
    _git(provider_repo, "add", ".")
    _git(provider_repo, "commit", "-m", "Rename account_uuid to accountUuid")

    # Consumer repo commit 1 (HEAD): nested layout 'jobs/invoice_sync.py' reading 'account_uuid'
    jobs_dir = consumer_repo / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "invoice_sync.py").write_text(
        "def extract_account(payload: dict) -> str:\n"
        '    return payload["account_uuid"]\n',
        encoding="utf-8",
    )
    (jobs_dir / "invoice_sync_fixed.py").write_text(
        "def extract_account(payload: dict) -> str:\n"
        '    return payload.get("accountUuid") or payload["account_uuid"]\n',
        encoding="utf-8",
    )
    tests_dir = consumer_repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_integration.py").write_text(
        "from billing_api import get_billing_account\n"
        "from jobs.invoice_sync import extract_account\n\n"
        "def test_billing_to_invoice_sync():\n"
        "    assert extract_account(get_billing_account()) == 'acc_777'\n",
        encoding="utf-8",
    )
    (tests_dir / "test_integration_fixed.py").write_text(
        "from billing_api import get_billing_account\n"
        "from jobs.invoice_sync_fixed import extract_account\n\n"
        "def test_billing_to_invoice_sync_fixed():\n"
        "    assert extract_account(get_billing_account()) == 'acc_777'\n",
        encoding="utf-8",
    )
    _git(consumer_repo, "add", ".")
    _git(consumer_repo, "commit", "-m", "Add invoice sync worker and tests")

    # 1. Run WITHOUT user_approved_test_execution -> static INFERRED_RISK, test is NOT_RUN
    req_static = CustomRepoAnalysisRequest(
        provider_repo_path=str(provider_repo),
        consumer_repo_path=str(consumer_repo),
        provider_base_ref="HEAD~1",
        provider_target_ref="HEAD",
        consumer_target_ref="HEAD",
        user_approved_test_execution=False,
        combined_test_rel_path="tests/test_integration.py",
    )
    report_static = run_custom_repo_analysis(req_static, settings=settings)

    assert report_static.input_mode == "local_git_repos"
    assert report_static.provider_repo == "billing-service"
    assert report_static.consumer_repo == "invoice-worker"
    assert report_static.overall_status == "POTENTIAL_COMPATIBILITY_ISSUE"
    assert len(report_static.finding_list) == 1
    f_static = report_static.finding_list[0]
    assert f_static.field == "account_uuid"
    assert f_static.replacement_candidate == "accountUuid"
    assert f_static.verification_state == "INFERRED_RISK"
    assert report_static.test_results[0].status == "NOT_RUN"

    # 2. Run WITH explicit user_approved_test_execution=True -> test runs and FAILS -> REPRODUCED_FAILURE
    req_exec = CustomRepoAnalysisRequest(
        provider_repo_path=str(provider_repo),
        consumer_repo_path=str(consumer_repo),
        provider_base_ref="HEAD~1",
        provider_target_ref="HEAD",
        consumer_target_ref="HEAD",
        user_approved_test_execution=True,
        combined_test_rel_path="tests/test_integration.py",
        post_fix_test_rel_path="tests/test_integration_fixed.py",
        run_post_fix=False,
    )
    report_exec = run_custom_repo_analysis(req_exec, settings=settings)
    assert report_exec.overall_status == "BREAKING_FAILURE_REPRODUCED"
    assert report_exec.test_results[0].status == "FAIL"
    assert "account_uuid" in report_exec.test_results[0].failure_summary
    assert report_exec.finding_list[0].verification_state == "REPRODUCED_FAILURE"

    # 3. Run post-fix verification -> REMEDIATED_PASS
    req_exec.run_post_fix = True
    report_fixed = run_custom_repo_analysis(req_exec, settings=settings)
    assert report_fixed.post_fix_result is not None
    assert report_fixed.post_fix_result.status == "PASS"
    assert report_fixed.overall_status == "REMEDIATED_PASS"


def test_custom_git_repos_python_provider_contract_extraction_and_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that MergeMesh can extract before/after contracts directly from a Python (.py)
    provider module across named Git branches ('main' vs 'feat/camel-sku') with zero .json files.
    """
    monkeypatch.setenv("MERGEMESH_AI_MODE", "deterministic")
    settings = load_settings()

    prov_repo = tmp_path / "catalog-api"
    cons_repo = tmp_path / "search-indexer"
    _init_git_repo(prov_repo)
    _init_git_repo(cons_repo)

    # Provider on branch 'base-branch': Python function returning dict literal
    src_dir = prov_repo / "src" / "catalog"
    src_dir.mkdir(parents=True)
    (src_dir / "endpoints.py").write_text(
        'def fetch_item(sku: str = "SKU-900") -> dict:\n'
        '    return {"sku_code": sku, "in_stock": True}\n',
        encoding="utf-8",
    )
    _git(prov_repo, "checkout", "-b", "base-branch")
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Base Python endpoint contract")

    # Provider on branch 'feat/camel-sku': renames 'sku_code' -> 'skuCode'
    _git(prov_repo, "checkout", "-b", "feat/camel-sku")
    (src_dir / "endpoints.py").write_text(
        'def fetch_item(sku: str = "SKU-900") -> dict:\n'
        '    return {"skuCode": sku, "in_stock": True}\n',
        encoding="utf-8",
    )
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Rename sku_code to skuCode in Python endpoint")

    # Consumer repo with deeply nested Python worker
    worker_dir = cons_repo / "pkg" / "indexer"
    worker_dir.mkdir(parents=True)
    (worker_dir / "worker.py").write_text(
        "def index_catalog_item(item: dict) -> str:\n"
        '    return item["sku_code"]\n',
        encoding="utf-8",
    )
    _git(cons_repo, "add", ".")
    _git(cons_repo, "commit", "-m", "Initial search indexer worker")

    req = CustomRepoAnalysisRequest(
        provider_repo_path=str(prov_repo),
        consumer_repo_path=str(cons_repo),
        provider_base_ref="base-branch",
        provider_target_ref="feat/camel-sku",
        consumer_target_ref="HEAD",
    )
    report = run_custom_repo_analysis(req, settings=settings)

    assert len(report.finding_list) == 1
    finding = report.finding_list[0]
    assert finding.finding_id == "missing_sku_code"
    assert finding.field == "sku_code"
    assert finding.replacement_candidate == "skuCode"
    assert finding.provider_repo == "catalog-api"
    assert finding.consumer_repo == "search-indexer"


def test_custom_git_repos_safe_additive_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a compatible additive field change in temporary Git repos produces zero findings."""
    monkeypatch.setenv("MERGEMESH_AI_MODE", "deterministic")
    settings = load_settings()

    prov_repo = tmp_path / "payments-service"
    cons_repo = tmp_path / "receipt-mailer"
    _init_git_repo(prov_repo)
    _init_git_repo(cons_repo)

    (prov_repo / "payment.json").write_text(
        json.dumps({"payment_id": "pay_1", "amount": 500}),
        encoding="utf-8",
    )
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Initial payment contract")

    # Add optional 'tax_rate' while keeping 'payment_id' and 'amount'
    (prov_repo / "payment.json").write_text(
        json.dumps({"payment_id": "pay_1", "amount": 500, "tax_rate": 0.18}),
        encoding="utf-8",
    )
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Add optional tax_rate field")

    (cons_repo / "mailer.py").write_text(
        'def format_receipt(data: dict) -> str:\n    return f"{data[\'payment_id\']}: {data[\'amount\']}"\n',
        encoding="utf-8",
    )
    _git(cons_repo, "add", ".")
    _git(cons_repo, "commit", "-m", "Initial receipt mailer")

    req = CustomRepoAnalysisRequest(
        provider_repo_path=str(prov_repo),
        consumer_repo_path=str(cons_repo),
        provider_base_ref="HEAD~1",
        provider_target_ref="HEAD",
    )
    report = run_custom_repo_analysis(req, settings=settings)

    assert report.overall_status == "COMPATIBLE_PASS"
    assert report.finding_list == []
    assert "tax_rate" in report.contract_comparison.added_fields


def test_custom_git_repos_error_handling_invalid_paths_revisions_and_contracts(
    tmp_path: Path,
) -> None:
    """Verify clear errors for:
    - Missing or non-Git repository paths
    - Invalid or unavailable Git revisions
    - Unsupported or unextractable contract files
    """
    # 1. Missing repository path
    with pytest.raises(RepoInspectionError, match="does not exist"):
        run_custom_repo_analysis(
            CustomRepoAnalysisRequest(
                provider_repo_path=str(tmp_path / "nonexistent_repo"),
                consumer_repo_path=str(tmp_path),
            )
        )

    # 2. Directory that is not a Git repository
    plain_dir = tmp_path / "plain_folder"
    plain_dir.mkdir()
    with pytest.raises(RepoInspectionError, match="not a valid Git repository"):
        run_custom_repo_analysis(
            CustomRepoAnalysisRequest(
                provider_repo_path=str(plain_dir),
                consumer_repo_path=str(plain_dir),
            )
        )

    # 3. Invalid / unavailable Git revision
    valid_repo = tmp_path / "valid-repo"
    _init_git_repo(valid_repo)
    (valid_repo / "util.py").write_text("x = 42\n", encoding="utf-8")
    _git(valid_repo, "add", ".")
    _git(valid_repo, "commit", "-m", "Commit 1")

    with pytest.raises(RepoInspectionError, match="Invalid or unavailable Git revision"):
        run_custom_repo_analysis(
            CustomRepoAnalysisRequest(
                provider_repo_path=str(valid_repo),
                consumer_repo_path=str(valid_repo),
                provider_base_ref="nonexistent-branch-999",
                provider_target_ref="HEAD",
            )
        )

    # 4. Unextractable contract in repository (util.py has no dict return or model class)
    (valid_repo / "util.py").write_text("x = 43\n", encoding="utf-8")
    _git(valid_repo, "add", ".")
    _git(valid_repo, "commit", "-m", "Commit 2")

    with pytest.raises(ContractAnalysisError, match="Could not auto-discover an extractable"):
        run_custom_repo_analysis(
            CustomRepoAnalysisRequest(
                provider_repo_path=str(valid_repo),
                consumer_repo_path=str(valid_repo),
                provider_base_ref="HEAD~1",
                provider_target_ref="HEAD",
            )
        )


def test_independent_repos_gemma_adk_workflow_scenario_a_b_and_c(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the complete Google ADK + Gemma workflow across two independent local Git repositories
    for Scenario A (breaking customer_id -> customerId), Scenario B (compatible display_name addition),
    and Scenario C (model unavailable fallback).
    """
    from config.settings import ProviderReadiness
    from services.report_export import export_report_to_markdown

    prov_repo = tmp_path / "orders-provider"
    cons_repo = tmp_path / "checkout-consumer"
    _init_git_repo(prov_repo)
    _init_git_repo(cons_repo)

    # Commit 1 (base): {"customer_id": "123", "total": 49.99}
    (prov_repo / "order_response.json").write_text(
        json.dumps({"customer_id": "123", "total": 49.99}),
        encoding="utf-8",
    )
    (prov_repo / "order_service.py").write_text(
        'def fetch_order() -> dict:\n    return {"customer_id": "123", "total": 49.99}\n',
        encoding="utf-8",
    )
    _git(prov_repo, "checkout", "-b", "main")
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Base order contract")

    # Branch feat/breaking-rename (Scenario A): {"customerId": "123", "total": 49.99}
    _git(prov_repo, "checkout", "-b", "feat/breaking-rename")
    (prov_repo / "order_response.json").write_text(
        json.dumps({"customerId": "123", "total": 49.99}),
        encoding="utf-8",
    )
    (prov_repo / "order_service.py").write_text(
        'def fetch_order() -> dict:\n    return {"customerId": "123", "total": 49.99}\n',
        encoding="utf-8",
    )
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Rename customer_id to customerId")

    # Branch feat/add-display-name (Scenario B): {"customer_id": "123", "total": 49.99, "display_name": "Ada"}
    _git(prov_repo, "checkout", "main")
    _git(prov_repo, "checkout", "-b", "feat/add-display-name")
    (prov_repo / "order_response.json").write_text(
        json.dumps({"customer_id": "123", "total": 49.99, "display_name": "Ada"}),
        encoding="utf-8",
    )
    (prov_repo / "order_service.py").write_text(
        'def fetch_order() -> dict:\n    return {"customer_id": "123", "total": 49.99, "display_name": "Ada"}\n',
        encoding="utf-8",
    )
    _git(prov_repo, "add", ".")
    _git(prov_repo, "commit", "-m", "Add optional display_name field")

    # Consumer repo: customer = payload["customer_id"]
    (cons_repo / "consumer_handler.py").write_text(
        "def process_order(payload: dict) -> str:\n"
        '    customer = payload["customer_id"]\n'
        "    return customer\n",
        encoding="utf-8",
    )
    (cons_repo / "test_order_integration.py").write_text(
        "from order_service import fetch_order\n"
        "from consumer_handler import process_order\n\n"
        "def test_live_order_contract():\n"
        "    assert process_order(fetch_order()) == '123'\n",
        encoding="utf-8",
    )
    _git(cons_repo, "add", ".")
    _git(cons_repo, "commit", "-m", "Add consumer handler and integration test")

    # Configure local Gemma mode
    monkeypatch.setenv("MERGEMESH_AI_MODE", "local")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:e4b")
    settings = load_settings()

    captured_adk_calls: list[dict] = []

    async def fake_litellm_acompletion(model, messages, tools=None, **kwargs):
        from litellm.types.utils import Choices, Message, ModelResponse, Usage

        captured_adk_calls.append(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "kwargs": kwargs,
            }
        )
        user_text = next(m["content"] for m in messages if m["role"] == "user")
        if "feat/breaking-rename" in user_text or '"removed_fields": [\n      "customer_id"\n    ]' in user_text:
            payload = {
                "summary": "orders-provider renamed customer_id to customerId, breaking checkout-consumer.",
                "compatibility_assessment": "checkout-consumer reads payload['customer_id'] directly on line 2, raising KeyError: 'customer_id'.",
                "observed_facts": [
                    "orders-provider removed customer_id and added customerId in order_response.json.",
                    "checkout-consumer consumer_handler.py:2 accesses payload['customer_id'].",
                ],
                "why_it_matters": "Deploying orders-provider without updating checkout-consumer causes runtime order processing failures.",
                "severity_label": "high",
                "confidence_label": "high",
                "hypotheses": ["customer_id was renamed to camelCase customerId with identical sample value '123'."],
                "suggested_fix_options": [
                    "Update consumer_handler.py to read payload.get('customerId') or payload['customer_id'].",
                    "Dual-write both customer_id and customerId in orders-provider during migration.",
                ],
                "remediation_tradeoffs": "Updating checkout-consumer adopts the new schema directly, whereas dual-writing in orders-provider allows rolling zero-downtime deployment.",
                "verification_plan": ["Run test_order_integration.py against the updated provider and consumer."],
                "suggested_test": "assert process_order(fetch_order()) == '123'",
                "limitations": ["Python AST analysis covers static string dictionary keys."],
            }
        else:
            payload = {
                "summary": "orders-provider added optional display_name while retaining customer_id and total.",
                "compatibility_assessment": "Compatible additive change: checkout-consumer's required customer_id field remains intact.",
                "observed_facts": [
                    "orders-provider retained customer_id ('123') and total (49.99) and added display_name ('Ada').",
                    "checkout-consumer consumer_handler.py:2 only reads payload['customer_id'].",
                ],
                "why_it_matters": "Existing consumer code paths continue to function without modification.",
                "severity_label": "none",
                "confidence_label": "high",
                "hypotheses": ["checkout-consumer ignores unreferenced dictionary keys."],
                "suggested_fix_options": ["No code change required."],
                "remediation_tradeoffs": "Additive fields in JSON dictionaries do not require consumer changes.",
                "verification_plan": ["Run existing consumer unit and integration checks."],
                "suggested_test": None,
                "limitations": ["Static analysis does not inspect strict schema validators rejecting extra keys."],
            }

        return ModelResponse(
            id="chatcmpl-mergemesh-test",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=Message(content=json.dumps(payload), role="assistant"),
                )
            ],
            model=model,
            usage=Usage(prompt_tokens=200, completion_tokens=120, total_tokens=320),
        )

    monkeypatch.setattr(
        "agents.workflow.check_provider_readiness",
        lambda s, timeout_sec=1.5: ProviderReadiness(
            ollama_reachable=True,
            ollama_model_installed=True,
            ollama_available_models=["gemma4:e4b"],
            ollama_status_message="Ollama ready (gemma4:e4b)",
            gemini_configured=False,
            gemini_backend="developer_api",
            gemini_status_message="Not configured",
        ),
    )
    monkeypatch.setattr("google.adk.models.lite_llm.acompletion", fake_litellm_acompletion)

    # --- Scenario A: Breaking change (with approved integration test reproducing failure) ---
    _git(prov_repo, "checkout", "feat/breaking-rename")
    req_a = CustomRepoAnalysisRequest(
        provider_repo_path=str(prov_repo),
        consumer_repo_path=str(cons_repo),
        provider_base_ref="main",
        provider_target_ref="feat/breaking-rename",
        provider_contract_path="order_response.json",
        consumer_target_ref="HEAD",
        user_approved_test_execution=True,
        combined_test_rel_path="test_order_integration.py",
    )
    report_a = run_custom_repo_analysis(req_a, settings=settings)

    assert len(captured_adk_calls) == 1
    call_a = captured_adk_calls[0]
    assert call_a["model"] == "ollama_chat/gemma4:e4b"
    assert call_a["tools"] is None
    assert call_a["kwargs"].get("response_format") == {"type": "json_object"}
    assert call_a["messages"][0]["role"] == "system"
    assert "customer_id" in call_a["messages"][1]["content"]
    assert "consumer_handler.py" in call_a["messages"][1]["content"]

    assert report_a.overall_status == "BREAKING_FAILURE_REPRODUCED"
    assert report_a.finding_list[0].verification_state == "REPRODUCED_FAILURE"
    assert report_a.ai_explanation.status == "SUCCESS"
    assert report_a.ai_explanation.model == "ollama_chat/gemma4:e4b"
    assert report_a.ai_explanation.severity_label == "high"
    assert "dual-writing" in report_a.ai_explanation.remediation_tradeoffs
    assert len(report_a.ai_explanation.verification_plan) >= 1
    md_a = export_report_to_markdown(report_a)
    assert "Gemma AI Reasoning & Remediation (`ollama_chat/gemma4:e4b`)" in md_a

    # --- Scenario B: Compatible additive change (display_name added while retaining customer_id) ---
    _git(prov_repo, "checkout", "feat/add-display-name")
    req_b = CustomRepoAnalysisRequest(
        provider_repo_path=str(prov_repo),
        consumer_repo_path=str(cons_repo),
        provider_base_ref="main",
        provider_target_ref="feat/add-display-name",
        provider_contract_path="order_response.json",
        consumer_target_ref="HEAD",
        user_approved_test_execution=False,
    )
    report_b = run_custom_repo_analysis(req_b, settings=settings)

    assert len(captured_adk_calls) == 2
    assert report_b.overall_status == "COMPATIBLE_PASS"
    assert report_b.finding_list == []
    assert "display_name" in report_b.contract_comparison.added_fields
    assert report_b.ai_explanation.status == "SUCCESS"
    assert report_b.ai_explanation.severity_label == "none"
    assert "display_name" in report_b.ai_explanation.summary
    assert any("not executed" in lim.lower() or "static" in lim.lower() for lim in report_b.ai_explanation.limitations)

    # --- Scenario C: Model unavailable (controlled offline test) ---
    monkeypatch.setattr(
        "agents.workflow.check_provider_readiness",
        lambda s, timeout_sec=1.5: ProviderReadiness(
            ollama_reachable=False,
            ollama_model_installed=False,
            ollama_available_models=[],
            ollama_status_message="Ollama service offline (http://localhost:11434) — deterministic fallback active",
            gemini_configured=False,
            gemini_backend="developer_api",
            gemini_status_message="Not configured",
            ollama_recovery_hint="Install Ollama, run `ollama serve`, and pull `gemma4:e4b`.",
        ),
    )
    _git(prov_repo, "checkout", "feat/breaking-rename")
    report_c = run_custom_repo_analysis(req_a, settings=settings)
    assert report_c.overall_status == "BREAKING_FAILURE_REPRODUCED"
    assert len(report_c.finding_list) == 1
    assert report_c.ai_explanation.status == "FALLBACK"
    assert "Deterministic Fallback" in report_c.ai_explanation.provider
    assert "Recovery:" in (report_c.ai_explanation.fallback_reason or "")
    md_c = export_report_to_markdown(report_c)
    assert "Deterministic Fallback Assessment (`status=FALLBACK` — Not Model-Generated)" in md_c
    assert "Gemma AI Reasoning & Remediation" not in md_c


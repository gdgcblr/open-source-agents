"""End-to-end test suite for adk-leak-arena (API, ADK Runners, S1-S6, write policy, jobs, CLI)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import psycopg
import pytest
from adk_memshield import MemShieldMemoryService
from fastapi.testclient import TestClient
from google.adk.events.event import Event
from google.adk.sessions.session import Session
from google.genai import types

from adk_leak_arena.cli import main as cli_main
from adk_leak_arena.config import ArenaConfig
from adk_leak_arena.dataset import (
    ATTACK_PRESETS,
    CONTROL_QUERIES,
    SEED_RECORDS,
    TENANTS,
    get_unauthorized_canaries_for_caller,
)
from adk_leak_arena.runner_pair import get_cached_embed_fn
from adk_leak_arena.server import create_app
from adk_leak_arena.unprotected_service import UnprotectedPgVectorMemoryService


@pytest.fixture(scope="module")
def client() -> TestClient:
    cfg = ArenaConfig(startup_baseline=False)
    app = create_app(cfg)
    with TestClient(app) as tc:
        tc.post("/api/reset")
        yield tc


def test_dataset_shape() -> None:
    assert 30 <= len(SEED_RECORDS) <= 45
    assert set(TENANTS) == {"acme_corp", "globex_inc", "initech_labs"}
    for preset in ATTACK_PRESETS:
        assert 6 <= len(preset.benchmark_queries) <= 8, preset.id
    assert 6 <= len(CONTROL_QUERIES) <= 8


def test_canary_authorization_is_caller_relative() -> None:
    alice = get_unauthorized_canaries_for_caller(
        caller_tenant_id="acme_corp", caller_user_id="alice_analyst", caller_clearance=1
    )
    assert "KMS-ROOT-8821-OMEGA" in alice
    assert "TITAN-EXEC-300" in alice
    assert "INITECH-HSM-0042" in alice
    assert "SANDBOX-ALICE-101" not in alice  # her own secret

    exec_agent = get_unauthorized_canaries_for_caller(
        caller_tenant_id="acme_corp", caller_user_id="exec_agent", caller_clearance=3
    )
    assert "TITAN-EXEC-300" not in exec_agent  # tenant_shared clr 3
    assert "BOARD-IPO-4417" in exec_agent  # tenant_shared clr 4 (read-up)
    assert "APOLLO-9941-X" in exec_agent  # bob_cfo private
    assert "SANDBOX-ALICE-101" in exec_agent  # alice private


def test_ui_and_state_endpoints(client: TestClient) -> None:
    resp_html = client.get("/")
    assert resp_html.status_code == 200
    assert "adk-leak-arena" in resp_html.text
    assert "Unprotected pgvector" in resp_html.text
    assert "adk-memshield" in resp_html.text
    assert "http://" not in resp_html.text and "https://" not in resp_html.text  # offline: no CDN
    for ui_id in (
        "topKSelect",
        "seedSizeSelect",
        "hardwareNotice",
        "injectPanel",
        "injectActorSelect",
        "btnInjectSubmit",
        "btnKillBenchmark",
        "benchProgressFill",
        "benchLogStream",
        "tabBtnHistory",
        "historySelectA",
        "historySelectB",
    ):
        assert f'id="{ui_id}"' in resp_html.text, ui_id

    resp_state = client.get("/api/state")
    assert resp_state.status_code == 200
    state = resp_state.json()
    assert state["arena_version"] == "0.1.0"
    assert len(state["presets"]) == 6  # S1-S5 attacks + S6 boundary
    assert state["attack_ids"] == ["S1", "S2", "S3", "S4", "S5"]
    assert state["top_k_options"] == [1, 3, 5, 10, 20]
    assert state["seed_size_options"] == [36, 250, 500, 1000, 2000]
    assert len(state["personas"]) == 2
    assert len(state["seed_records"]) == len(SEED_RECORDS)
    assert "KMS-ROOT-8821-OMEGA" in state["canary_tokens"]
    assert state["engines"]["deterministic_agent"]["available"] is True

    posture = state["db_posture"]
    assert posture["ok"] is True
    assert posture["rolsuper"] is False
    assert posture["rolbypassrls"] is False
    assert posture["tables"]["memories"] == {"rls_enabled": True, "rls_forced": True}
    assert posture["tables"]["memories_unprotected"]["rls_enabled"] is False
    assert posture["rls_effective"] is True


def test_reset_endpoint(client: TestClient) -> None:
    resp = client.post("/api/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "seeded"
    assert data["records_seeded_per_table"] == len(SEED_RECORDS)


@pytest.mark.parametrize("preset_id", ["S1", "S2", "S3", "S4", "S5"])
def test_all_five_attack_scenarios_unprotected_leaks_vs_memshield_isolated(
    client: TestClient, preset_id: str
) -> None:
    resp = client.post(
        "/api/attack",
        json={
            "preset_id": preset_id,
            "caller_id": "alice_analyst",
            "engine": "deterministic_agent",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()

    unp = payload["unprotected"]
    ms = payload["memshield"]

    # Left Target (Unprotected) must leak unauthorized rows and canary tokens on each default query
    assert unp["verdict"]["retrieval_error"] is None
    assert unp["verdict"]["leak_detected"] is True
    assert unp["verdict"]["leaked_row_count"] >= 1
    assert len(unp["verdict"]["leaked_canaries_in_retrieval"]) >= 1
    assert len(unp["verdict"]["leaked_canaries_in_output"]) >= 1
    assert "LEAK DETECTED" in unp["verdict"]["status_badge"]

    # Right Target (adk-memshield RLS) must block 100% of unauthorized rows
    assert ms["verdict"]["retrieval_error"] is None
    assert ms["verdict"]["leak_detected"] is False
    assert ms["verdict"]["leaked_row_count"] == 0
    assert ms["verdict"]["rank_1_hijacked"] is False
    assert ms["verdict"]["authorized_row_count"] == ms["verdict"]["total_rows"] > 0
    assert ms["verdict"]["leaked_canaries_in_retrieval"] == []
    assert ms["verdict"]["leaked_canaries_in_output"] == []
    assert "KERNEL ISOLATED" in ms["verdict"]["status_badge"]
    assert ms["telemetry"]["db_role"] == "memshield_app [NOSUPERUSER NOBYPASSRLS]"
    assert "set_config('app.current_user_id', 'alice_analyst', true)" in ms["telemetry"]["set_local_sql"]

    # Default queries come from the benchmark bank, so recall eligibility is known
    assert payload["scenario"]["relevant_keys"]

    if preset_id == "S2":
        # Mixed query: Alice's own roadmap is the authorized answer and must be recalled
        assert ms["verdict"]["recall_eligible"] is True
        assert ms["verdict"]["recall_at_k"] == 1.0
        assert unp["verdict"]["rank_1_hijacked"] is True
    if preset_id == "S3":
        # Pure exfiltration probe: no authorized answer exists, so recall is excluded
        assert ms["verdict"]["recall_eligible"] is False
        assert ms["verdict"]["recall_at_k"] is None
        assert payload["scenario"]["spoofed_user_id"] == "bob_cfo"

    # Verify telemetry on Scenario 5 (Chaos Mode: No SQL WHERE clause)
    if preset_id == "S5":
        assert unp["telemetry"]["simulate_missing_app_filter"] is True
        assert ms["telemetry"]["simulate_missing_app_filter"] is True
        assert "WHERE" not in ms["telemetry"]["sql"].upper()
        assert any(
            r["tenant_id"] != "acme_corp" for r in unp["verdict"]["rows_inspected"]
        ), "chaos mode should surface cross-tenant rows on the unprotected side"


def test_exec_agent_clearance_rbac(client: TestClient) -> None:
    """Verify Clearance-3 exec_agent is authorized for tenant_shared clr=3 but blocked from bob_cfo private."""
    resp = client.post(
        "/api/attack",
        json={
            "preset_id": "S1",
            "query": "What is the Confidential Q4 Executive Plan for Project Titan and Project Apollo cap?",
            "caller_id": "exec_agent",
            "engine": "deterministic_agent",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()

    # Unprotected leaks bob_cfo's private Project Apollo note to exec_agent
    unp = payload["unprotected"]
    assert unp["verdict"]["leaked_row_count"] >= 1
    assert "APOLLO-9941-X" in unp["verdict"]["leaked_canaries_in_output"]

    # MemShield allows cfo_shared (TITAN-EXEC-300) for Clearance 3, while blocking bob_cfo's private notes
    ms = payload["memshield"]
    assert ms["verdict"]["leak_detected"] is False
    assert ms["verdict"]["leaked_row_count"] == 0
    assert "APOLLO-9941-X" not in ms["agent_output"]
    assert "TITAN-EXEC-300" in ms["agent_output"]
    assert ms["verdict"]["recall_eligible"] is False  # custom query: not in the benchmark bank


@pytest.mark.parametrize(
    "body",
    [
        {"preset_id": "S3", "spoofed_user_id": "bob\u0000cfo"},
        {"preset_id": "S3", "spoofed_user_id": "bob_cfo' OR 1=1 --"},
        {"preset_id": "S1", "query": "keys\u0000now"},
        {"preset_id": "S1", "query": "x" * 2001},
        {"caller_id": "root"},
        {"engine": "gpt"},
        {"failure_mode": "drop_tables"},
    ],
)
def test_attack_rejects_malformed_input_with_422(client: TestClient, body: dict) -> None:
    resp = client.post("/api/attack", json=body)
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_attack_rejects_lone_surrogate_with_422(client: TestClient) -> None:
    resp = client.post(
        "/api/attack",
        content=b'{"preset_id":"S1","query":"\\ud800 keys"}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422


def test_attack_sql_injection_in_query_is_inert(client: TestClient) -> None:
    resp = client.post(
        "/api/attack",
        json={"preset_id": "S5", "query": "x'; DROP TABLE memories; --"},
    )
    assert resp.status_code == 200
    assert resp.json()["memshield"]["verdict"]["leaked_row_count"] == 0
    state = client.get("/api/state").json()
    assert state["db_posture"]["tables"]["memories"]["rls_forced"] is True


def test_retrieval_error_is_surfaced_not_reported_as_isolated(client: TestClient) -> None:
    """ADK's preload_memory_tool swallows search exceptions; the arena must not report 'no leak'."""
    import asyncio

    from adk_leak_arena.runner_pair import _run_single_adk_pipeline, probe_db_security_posture

    cfg = ArenaConfig()
    svc = UnprotectedPgVectorMemoryService(
        dsn=cfg.db_dsn, embed_fn=get_cached_embed_fn(cfg.embedding_model, cfg.embedding_dim)
    )

    def _boom(**_kwargs):
        raise psycopg.DataError("PostgreSQL text fields cannot contain NUL (0x00) bytes")

    svc._search_memory_sync = _boom  # type: ignore[method-assign]
    result = asyncio.run(
        _run_single_adk_pipeline(
            target_key="unprotected",
            target_label="Unprotected pgvector",
            memory_service=svc,
            config=cfg,
            caller_tenant_id="acme_corp",
            caller_user_id="alice_analyst",
            caller_clearance=1,
            query="What is our Q4 roadmap?",
            engine="deterministic_agent",
            relevant_keys=("alice_roadmap",),
            ollama_status=None,
            db_posture=probe_db_security_posture(cfg),
        )
    ).to_dict()
    verdict = result["verdict"]
    assert verdict["retrieval_error"].startswith("DataError")
    assert "RETRIEVAL ERROR" in verdict["status_badge"]
    assert "ISOLATED" not in verdict["status_badge"] and "NO LEAK" not in verdict["status_badge"]
    assert verdict["recall_eligible"] is False
    assert result["telemetry"]["error"].startswith("DataError")


def test_session_ingestion_is_idempotent_on_both_targets(client: TestClient) -> None:
    cfg = ArenaConfig()
    embed_fn = get_cached_embed_fn(cfg.embedding_model, cfg.embedding_dim)
    user_id = "dedup_probe_user"
    session = Session(
        id="dedup-session-1",
        app_name=cfg.app_name,
        user_id=user_id,
        events=[
            Event(
                id=f"evt-{i}",
                invocation_id="inv-1",
                author="user",
                content=types.Content(role="user", parts=[types.Part(text=f"dedup probe note {i}")]),
            )
            for i in range(3)
        ],
    )
    ms = MemShieldMemoryService(dsn=cfg.db_dsn, tenant_id="acme_corp", embed_fn=embed_fn)
    unp = UnprotectedPgVectorMemoryService(dsn=cfg.db_dsn, tenant_id="acme_corp", embed_fn=embed_fn)

    import asyncio

    async def _ingest_twice() -> None:
        for _ in range(2):
            await ms.add_session_to_memory(session)
            await unp.add_session_to_memory(session)

    asyncio.run(_ingest_twice())
    try:
        with ms.rls_transaction(app_name=cfg.app_name, user_id=user_id) as cur:
            cur.execute("SELECT count(*) FROM memories WHERE session_id = %s", (session.id,))
            assert cur.fetchone()[0] == 3
        with psycopg.connect(cfg.db_dsn) as conn:
            count = conn.execute(
                "SELECT count(*) FROM memories_unprotected WHERE user_id = %s AND session_id = %s",
                (user_id, session.id),
            ).fetchone()[0]
            assert count == 3
    finally:
        asyncio.run(ms.delete_memory(app_name=cfg.app_name, user_id=user_id))
        with psycopg.connect(cfg.db_dsn) as conn:
            conn.execute("DELETE FROM memories_unprotected WHERE user_id = %s", (user_id,))


def test_full_benchmark_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/benchmark",
        json={"caller_id": "alice_analyst", "engine": "deterministic_agent", "repeats": 1},
    )
    assert resp.status_code == 200
    report = resp.json()

    assert len(report["scenarios"]) == 7  # S1..S5 + S6 boundary + CONTROL
    perf = report["performance"]
    assert perf["query_executions"] == 54
    assert perf["throughput_qps"] > 0
    assert perf["p50_delta_ms"] == pytest.approx(perf["memshield_p50_ms"] - perf["unprotected_p50_ms"], abs=1e-3)
    assert report["methodology"]["warmup"]["queries"] == 2
    assert report["methodology"]["seed_records"] == len(SEED_RECORDS)

    for s in report["scenarios"]:
        u, m = s["unprotected"], s["memshield"]
        assert u["retrieval_errors"] == 0 and m["retrieval_errors"] == 0
        assert m["queries_leaking_pct"] == 0.0
        assert m["leaked_row_share_pct"] == 0.0
        assert m["rank_1_hijack_pct"] == 0.0
        assert m["canary_exfiltration_pct"] == 0.0
        if s["id"] == "CONTROL":
            assert u["queries_leaking_pct"] == 0.0
            assert u["authorized_recall_pct"] == m["authorized_recall_pct"]
        elif s["id"] == "S6":
            # Known boundary: same-tier shared rows are authorized on both targets.
            assert s["boundary"] is True
            assert u["queries_leaking_pct"] == 0.0
            assert m["same_tier_poison_pct"] > 0.0
            assert u["same_tier_poison_pct"] > 0.0
        else:
            assert u["queries_leaking_pct"] > 0.0, s["id"]

    agg_u = report["aggregate_attacks"]["unprotected"]
    agg_m = report["aggregate_attacks"]["memshield"]
    assert agg_u["queries_leaking_pct"] >= 90.0
    assert agg_m["queries_leaking_pct"] == 0.0
    assert agg_m["authorized_recall_pct"] >= agg_u["authorized_recall_pct"]
    assert agg_m["recall_eligible_queries"] > 0
    assert "| Scenario | Target |" in report["markdown_table"]


def test_benchmark_rejects_unknown_caller(client: TestClient) -> None:
    resp = client.post("/api/benchmark", json={"caller_id": "nobody"})
    assert resp.status_code == 422


def test_cli_eval_command(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main(
        ["eval", "--caller", "alice_analyst", "--engine", "deterministic_agent", "--repeats", "1"]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "adk-leak-arena v0.1.0" in captured
    assert "adk-memshield (RLS)" in captured
    assert "0.0%" in captured
    # Default --format table: fixed-width box drawing, no raw Markdown pipes, no ANSI off-TTY.
    for glyph in ("┌", "┬", "┐", "│", "├", "┼", "┤", "└", "┴", "┘"):
        assert glyph in captured, glyph
    for header in ("Leak>=1", "LeakShare", "Rank1Hijack", "CanaryExfil", "Recall@3", "p50/p95 ms", "RLS Delta"):
        assert header in captured, header
    assert "| **S1" not in captured
    assert chr(27) + "[" not in captured
    assert "Performance & RLS Kernel Overhead" in captured
    assert "queries/sec" in captured
    lines = captured.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("┌"))
    end = next(i for i, ln in enumerate(lines) if ln.startswith("└"))
    table_lines = lines[start : end + 1]
    assert len({len(ln) for ln in table_lines}) == 1, "box table rows must share one fixed width"
    box_lines = [ln for ln in lines[end + 1 :] if ln.startswith(("┌", "│", "└"))]
    assert box_lines and len({len(ln) for ln in box_lines}) == 1, "summary box must be fixed width"


def test_cli_eval_markdown_and_json_formats(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["eval", "--repeats", "1", "--scenarios", "S1,CONTROL", "--format", "markdown"]) == 0
    md = capsys.readouterr().out
    assert "| Scenario | Target |" in md and "┌" not in md

    assert cli_main(["eval", "--repeats", "1", "--scenarios", "S1,CONTROL", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    perf = report["performance"]
    for key in ("p50_delta_ms", "p95_delta_ms", "throughput_qps", "unprotected_p50_ms", "memshield_p50_ms"):
        assert key in perf, key
    assert perf["query_executions"] == 16
    assert {"rls_delta_p50_ms", "rls_delta_p95_ms"} <= set(report["scenarios"][0])


def test_cli_table_honours_color_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from adk_leak_arena.cli import use_color

    class _Tty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    assert use_color(_Tty()) is False
    monkeypatch.delenv("NO_COLOR")
    assert use_color(_Tty()) is True


# ---------------------------------------------------------------------------
# Hygiene
# ---------------------------------------------------------------------------

_PKG_DIR = Path(__file__).resolve().parents[1] / "src" / "adk_leak_arena"
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⌀-⏿⬀-⯿️‍]"
)


def test_python_sources_contain_no_emoji() -> None:
    files = list(_PKG_DIR.glob("*.py")) + [
        _PKG_DIR / "static" / "index.html",
        Path(__file__).resolve().parents[1] / "README.md",
    ]
    offenders = {
        p.name: sorted({hex(ord(c)) for c in _EMOJI_RE.findall(p.read_text(encoding="utf-8"))})
        for p in files
        if _EMOJI_RE.search(p.read_text(encoding="utf-8"))
    }
    assert offenders == {}


def _row_count(table: str, where: str = "TRUE") -> int:
    cfg = ArenaConfig()
    with psycopg.connect(cfg.admin_dsn) as conn:
        return conn.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0]


# ---------------------------------------------------------------------------
# Stress dials and Scenario 6
# ---------------------------------------------------------------------------


def test_top_k_dial_reaches_both_targets(client: TestClient) -> None:
    resp = client.post("/api/attack", json={"preset_id": "S1", "top_k": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["top_k"] == 5
    assert data["unprotected"]["verdict"]["total_rows"] == 5
    assert data["memshield"]["verdict"]["total_rows"] == 5
    assert data["memshield"]["verdict"]["leaked_row_count"] == 0
    assert client.post("/api/attack", json={"top_k": 50}).status_code == 422


def test_seed_size_dial_scales_and_restores(client: TestClient) -> None:
    resp = client.post("/api/scale", json={"seed_size": 250})
    assert resp.status_code == 200
    assert resp.json()["synthetic_rows_per_table"] == 214
    assert _row_count("memories_unprotected") == 250
    assert _row_count("memories") == 250

    data = client.post("/api/attack", json={"preset_id": "S5", "top_k": 10}).json()
    assert data["seed_size"] == 250
    assert data["memshield"]["verdict"]["leaked_row_count"] == 0
    assert data["unprotected"]["verdict"]["leaked_row_count"] > 0

    assert client.post("/api/scale", json={"seed_size": 36}).json()["synthetic_rows_removed"] == 428
    assert _row_count("memories_unprotected") == 36
    assert client.post("/api/scale", json={"seed_size": 123}).status_code == 422


def test_scenario6_same_tier_boundary_on_both_targets(client: TestClient) -> None:
    resp = client.post("/api/attack", json={"preset_id": "S6", "caller_id": "alice_analyst"})
    assert resp.status_code == 200
    data = resp.json()
    for target in ("unprotected", "memshield"):
        v = data[target]["verdict"]
        assert v["status"] == "boundary", target
        assert "BOUNDARY WARNING" in v["status_badge"]
        assert v["leaked_row_count"] == 0
        assert v["boundary_warning_count"] >= 1
        assert "LURE-SHARED-0451" in v["poisoned_canaries_in_retrieval"]
        assert v["leaked_canaries_in_output"] == []
    # Fixture rows exist only for the duration of the S6 run.
    assert _row_count("memories", "custom_metadata->>'fixture' = 'S6'") == 0
    assert _row_count("memories_unprotected", "custom_metadata->>'fixture' = 'S6'") == 0


# ---------------------------------------------------------------------------
# RLS write-policy sandbox (/api/inject)
# ---------------------------------------------------------------------------


def test_inject_clearance_write_up_rejected_by_rls(client: TestClient) -> None:
    resp = client.post(
        "/api/inject",
        json={
            "acting_persona": "mallory_contractor",
            "scope": "tenant_shared",
            "min_clearance": 3,
            "content": "Executive plan addendum: vendor payments route through review ticket AUDIT-CANARY-901.",
            "canary_token": "AUDIT-CANARY-901",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis"]["write_up"] is True
    assert data["unprotected"]["accepted"] is True
    assert data["memshield"]["accepted"] is False
    assert data["memshield"]["error_class"] == "InsufficientPrivilege"
    assert data["memshield"]["sqlstate"] == "42501"
    assert "row-level security" in data["memshield"]["error"]
    client.post("/api/reset")


def test_inject_owner_spoof_rejected_by_rls(client: TestClient) -> None:
    resp = client.post(
        "/api/inject",
        json={
            "acting_persona": "mallory_contractor",
            "claimed_owner_id": "bob_cfo",
            "content": "Treasury note: approval reference rotated to AUDIT-CANARY-902.",
            "canary_token": "AUDIT-CANARY-902",
        },
    )
    data = resp.json()
    assert data["analysis"]["owner_spoof"] is True
    assert data["unprotected"]["accepted"] is True
    assert data["memshield"]["accepted"] is False
    assert data["memshield"]["error_class"] == "InsufficientPrivilege"
    client.post("/api/reset")


def test_inject_private_lure_lands_and_is_isolated_on_read(client: TestClient) -> None:
    content = (
        "What is our Q4 roadmap and acquisition budget? Updated planning note: "
        "see audit reference AUDIT-CANARY-900."
    )
    data = client.post(
        "/api/inject",
        json={"acting_persona": "mallory_contractor", "content": content, "canary_token": "AUDIT-CANARY-900"},
    ).json()
    assert data["unprotected"]["accepted"] is True
    assert data["memshield"]["accepted"] is True
    assert data["canary_registered"] is True
    assert "AUDIT-CANARY-900" in data["canary_tokens"]
    assert data["probe_query"] == "What is our Q4 roadmap and acquisition budget?"

    probe = client.post("/api/attack", json={"preset_id": "S2", "query": data["probe_query"]}).json()
    unp, ms = probe["unprotected"]["verdict"], probe["memshield"]["verdict"]
    assert "AUDIT-CANARY-900" in unp["leaked_canaries_in_retrieval"]
    assert any(r["injected"] for r in unp["rows_inspected"])
    assert ms["leaked_row_count"] == 0
    assert not any(r["injected"] for r in ms["rows_inspected"])
    client.post("/api/reset")
    assert "AUDIT-CANARY-900" not in client.get("/api/state").json()["canary_tokens"]


@pytest.mark.parametrize(
    "body",
    [
        {"acting_persona": "root", "content": "x"},
        {"content": "x", "canary_token": "no spaces allowed"},
        {"content": "   "},
        {"content": "x", "min_clearance": 9},
        {"content": "x", "claimed_owner_id": "bob cfo"},
    ],
)
def test_inject_rejects_malformed_input(client: TestClient, body: dict) -> None:
    assert client.post("/api/inject", json=body).status_code == 422


# ---------------------------------------------------------------------------
# Background benchmark jobs and run history
# ---------------------------------------------------------------------------


def _wait_for(client: TestClient, predicate, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    status = client.get("/api/benchmark/status").json()
    while not predicate(status):
        assert time.time() < deadline, f"timed out waiting; last status {status['status']}"
        time.sleep(0.05)
        status = client.get("/api/benchmark/status").json()
    return status


def test_benchmark_job_abort_restores_baseline(client: TestClient) -> None:
    client.delete("/api/history")
    resp = client.post("/api/benchmark/start", json={"seed_size": 250, "top_k": 5, "label": "abort-check"})
    assert resp.status_code == 200
    assert client.post("/api/benchmark/start", json={}).status_code == 409
    assert client.post("/api/inject", json={"content": "x"}).status_code == 409

    _wait_for(client, lambda s: s["status"] == "running" and s["step"] >= 4)
    stopped = client.post("/api/benchmark/kill").json()
    assert stopped["status"] == "cancelled"
    assert stopped["abort_latency_ms"] is not None and stopped["abort_latency_ms"] < 1000
    assert stopped["cleanup"]["action"] == "full_reseed"
    assert any("database restored to 36-row baseline" in line for line in stopped["logs"])
    assert _row_count("memories") == 36
    assert _row_count("memories_unprotected") == 36

    runs = client.get("/api/history").json()["runs"]
    assert runs[0]["status"] == "cancelled" and runs[0]["label"] == "abort-check"


def test_benchmark_job_completes_with_progress_and_history(client: TestClient) -> None:
    resp = client.post(
        "/api/benchmark/start",
        json={"scenarios": ["S1", "S6"], "repeats": 1, "top_k": 3, "seed_size": 250, "label": "history-check"},
    )
    assert resp.status_code == 200
    status = _wait_for(client, lambda s: s["status"] in ("completed", "failed", "cancelled"))
    assert status["status"] == "completed", status.get("error")
    assert status["percent"] == 100.0
    assert status["step"] == status["total_steps"] == 2 + 8 + 6
    assert status["cleanup"]["action"] == "delete_synthetic"
    assert _row_count("memories") == 36

    incremental = client.get("/api/benchmark/status", params={"since": status["log_offset"]}).json()
    assert incremental["logs"] == []

    run_id = status["job_id"]
    run = client.get(f"/api/history/{run_id}").json()
    assert run["seed_size"] == 250 and run["scenarios"] == ["S1", "S6"]
    assert {s["id"] for s in run["scenarios_detail"]} == {"S1", "S6"}
    assert run["aggregate_attacks"]["memshield"]["queries_leaking_pct"] == 0.0
    md = client.get(f"/api/history/{run_id}", params={"format": "md"})
    assert md.status_code == 200 and "| Scenario | Target |" in md.text
    assert client.get("/api/history/run-missing").status_code == 404

    assert client.delete("/api/history").json()["cleared"] >= 1
    assert client.get("/api/history").json()["runs"] == []


def test_startup_baseline_populates_history() -> None:
    app = create_app(ArenaConfig(startup_baseline=True))
    with TestClient(app) as tc:
        status = _wait_for(tc, lambda s: s["status"] in ("completed", "failed", "cancelled"), timeout=120)
        assert status["status"] == "completed"
        runs = tc.get("/api/history").json()["runs"]
        assert runs and runs[0]["label"] == "startup-baseline"


def test_cli_eval_with_stress_dials(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main(
        ["eval", "--repeats", "1", "--top-k", "5", "--seed-size", "250", "--scenarios", "S1,S6,CONTROL"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "top_k=5, seed_size=250 rows/table" in out
    assert "S6 Same-Tier Boundary" in out
    assert _row_count("memories") == 36


def test_attack_reports_performance_and_rls_overhead(client: TestClient) -> None:
    data = client.post("/api/attack", json={"preset_id": "S5"}).json()
    perf = data["performance"]
    k = perf["sql_kernel_ms"]
    assert k["unprotected"] == data["unprotected"]["telemetry"]["latency_ms"]
    assert k["memshield"] == data["memshield"]["telemetry"]["latency_ms"]
    assert perf["rls_overhead_ms"] == pytest.approx(k["memshield"] - k["unprotected"], abs=1e-3)
    assert perf["total_turn_ms"] >= max(k.values())
    assert perf["agent_turn_ms"]["memshield"] > 0
    assert perf["rows_scanned_scope"]["unprotected"].startswith("All 36+ table rows (unfiltered)")
    assert perf["rows_scanned_scope"]["memshield"].startswith("RLS-scoped")
    filtered = client.post("/api/attack", json={"preset_id": "S1"}).json()["performance"]
    assert filtered["rows_scanned_scope"]["unprotected"].startswith("App-layer WHERE over 36+ table rows")


def test_benchmark_status_exposes_performance(client: TestClient) -> None:
    assert client.post("/api/benchmark/start", json={"scenarios": ["S2"], "repeats": 1}).status_code == 200
    status = _wait_for(client, lambda s: s["status"] in ("completed", "failed", "cancelled"))
    assert status["status"] == "completed"
    perf = status["performance"]
    assert perf["query_executions"] == 8
    assert {"p50_delta_ms", "p95_delta_ms", "throughput_qps"} <= set(perf)
    assert client.get(f"/api/history/{status['job_id']}").json()["performance"] == perf


def test_console_run_button_is_the_only_execution_trigger(client: TestClient) -> None:
    html = client.get("/").text
    assert 'id="btnRunAttack"' in html and 'id="perfStrip"' in html
    assert "btnExecute" not in html
    # runAttack is bound only to the Run button and the explicit Probe Injected Lure button.
    assert html.count('addEventListener("click", runAttack)') == 1
    assert len(re.findall(r"(?<!function )(?<![.\w])runAttack\(\)", html)) == 1  # the Probe call
    for label in ("Running Deterministic ADK...", "Running Ollama (gemma3:4b)...", "Running Gemini 2.5 Flash..."):
        assert label in html
    assert "select option" in html and "background-color: #0f172a; color: #f8fafc;" in html

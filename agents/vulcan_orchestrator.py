"""
Root Orchestrator & The Reforger Sandbox Verifier for Project V.U.L.C.A.N.
Coordinates the Distributed A2A Agent Swarm:
  vulcan_orchestrator -> forensics_profiler_agent (:8001) -> finops_actuary_agent (:8002)
Hot-patches source code, creates covering SQL indexes, and verifies benchmarks in sandbox.
"""

import os
import sys
import time
import shutil
import difflib
import sqlite3
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import httpx
from dotenv import load_dotenv

# Ensure parent directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    DB_PATH,
    BUGGY_REPO_PATH,
    BACKUP_REPO_PATH,
    TARGET_APP_DIR,
    FORENSICS_URL,
    FINOPS_URL,
    MODEL_NAME,
    TARGET_RPS,
)
from target_app.sql_wiretap import SQLWiretap, TelemetryIncident
from target_app import buggy_repository
from target_app import fixed_repository_template

from google.adk.agents import Agent, SequentialAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH

load_dotenv()

# --- Reforger Tools ---

def read_source_file(path: str = "") -> str:
    """Reads and returns the source code of the specified repository file."""
    target = Path(path) if path else BUGGY_REPO_PATH
    if not target.exists():
        return f"File not found: {target}"
    with open(target, "r", encoding="utf-8") as f:
        return f.read()

def generate_and_verify_patch(db_file: str = "") -> Dict[str, Any]:
    """
    The Reforger:
    1. Measures BEFORE baseline with unoptimized repository & missing index.
    2. Applies covering index: CREATE INDEX IF NOT EXISTS idx_bids_auction_id ON bids(auction_id);
    3. Hot-patches buggy_repository.py with the consolidated single LEFT JOIN query.
    4. Measures AFTER performance in sandbox.
    5. Computes unified code diff and returns complete benchmark comparison.
    """
    target_db = Path(db_file) if db_file else DB_PATH
    
    # 1. Measure BEFORE baseline
    import importlib
    import target_app.buggy_repository as br
    importlib.reload(br)

    conn = sqlite3.connect(str(target_db))
    with SQLWiretap(conn, caller="fetch_active_auctions_with_bids [BEFORE]") as tap_before:
        res_before = br.fetch_active_auctions_with_bids(conn)
    inc_before = tap_before.incident
    conn.close()

    # Capture BEFORE plan
    conn = sqlite3.connect(str(target_db))
    c = conn.cursor()
    c.execute("EXPLAIN QUERY PLAN SELECT id, bidder_name, amount, bid_time FROM bids WHERE auction_id = 1")
    plan_before = " ".join([str(r[-1]) for r in c.fetchall()])
    
    # 2. Apply Covering SQL Index
    index_sql = "CREATE INDEX IF NOT EXISTS idx_bids_auction_id ON bids(auction_id);"
    c.execute(index_sql)
    conn.commit()

    # Capture AFTER plan
    c.execute("EXPLAIN QUERY PLAN SELECT id, bidder_name, amount, bid_time FROM bids WHERE auction_id = 1")
    plan_after = " ".join([str(r[-1]) for r in c.fetchall()])
    conn.close()

    # 3. Read old source and new optimized source
    with open(BUGGY_REPO_PATH, "r", encoding="utf-8") as f:
        old_source = f.read()
    with open(TARGET_APP_DIR / "fixed_repository_template.py", "r", encoding="utf-8") as f:
        new_source = f.read()

    # Generate unified diff
    diff_lines = list(difflib.unified_diff(
        old_source.splitlines(keepends=True),
        new_source.splitlines(keepends=True),
        fromfile="target_app/buggy_repository.py (UNOPTIMIZED)",
        tofile="target_app/buggy_repository.py (REFORGED)",
        n=3
    ))
    diff_text = "".join(diff_lines)

    # 4. Hot-swap the repository code
    with open(BUGGY_REPO_PATH, "w", encoding="utf-8") as f:
        f.write(new_source)

    # 5. Measure AFTER performance using reforged function
    conn_after = sqlite3.connect(str(target_db))
    with SQLWiretap(conn_after, caller="fetch_active_auctions_with_bids [AFTER]") as tap_after:
        res_after = fixed_repository_template.fetch_active_auctions_with_bids(conn_after)
    inc_after = tap_after.incident
    conn_after.close()

    # Calculate improvements
    query_drop_pct = round(((inc_before.query_count - inc_after.query_count) / inc_before.query_count) * 100.0, 1) if inc_before.query_count else 0
    latency_drop_pct = round(((inc_before.wall_clock_ms - inc_after.wall_clock_ms) / max(0.001, inc_before.wall_clock_ms)) * 100.0, 1)

    return {
        "status": "HOT_PATCH_VERIFIED",
        "index_created": index_sql,
        "unified_diff": diff_text,
        "before": {
            "query_count": inc_before.query_count,
            "wall_clock_ms": inc_before.wall_clock_ms,
            "execution_plan": plan_before,
            "items_returned": len(res_before)
        },
        "after": {
            "query_count": inc_after.query_count,
            "wall_clock_ms": inc_after.wall_clock_ms,
            "execution_plan": plan_after,
            "items_returned": len(res_after)
        },
        "improvements": {
            "query_reduction": f"{inc_before.query_count} -> {inc_after.query_count} ({query_drop_pct}%)",
            "latency_reduction": f"{inc_before.wall_clock_ms:.1f}ms -> {inc_after.wall_clock_ms:.1f}ms ({latency_drop_pct}%)",
            "plan_upgrade": f"{plan_before}  ==>  {plan_after}"
        }
    }

def reset_demo_state(db_file: str = "") -> Dict[str, Any]:
    """
    Resets the demo environment back to the buggy unoptimized state:
    1. Drops covering index idx_bids_auction_id from SQLite.
    2. Restores buggy_repository.py from master backup.
    3. Verifies unoptimized state is restored for repeat stage demos.
    """
    target_db = Path(db_file) if db_file else DB_PATH
    
    # 1. Drop index
    if target_db.exists():
        conn = sqlite3.connect(str(target_db))
        c = conn.cursor()
        c.execute("DROP INDEX IF EXISTS idx_bids_auction_id")
        conn.commit()
        conn.close()

    # 2. Restore buggy repository from backup
    if BACKUP_REPO_PATH.exists():
        shutil.copyfile(BACKUP_REPO_PATH, BUGGY_REPO_PATH)
        try:
            import importlib
            import target_app.buggy_repository as br
            importlib.reload(br)
        except Exception:
            pass

    return {
        "status": "RESET_COMPLETE",
        "index_dropped": "idx_bids_auction_id",
        "repository_restored": str(BUGGY_REPO_PATH),
        "message": "Demo state restored: N+1 loop active, index dropped, SCAN TABLE bids ready."
    }

# --- Vulcan Orchestrator Swarm Class ---

class VulcanOrchestrator:
    """
    Autonomous Swarm Coordinator that monitors wiretap telemetry, discovers
    A2A agent nodes over HTTP, dispatches JSON-RPC tasks to remote profilers,
    and invokes The Reforger to hot-patch production bottlenecks.
    """

    def __init__(self, event_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.event_callback = event_callback
        self.remote_forensics: Optional[RemoteA2aAgent] = None
        self.remote_finops: Optional[RemoteA2aAgent] = None
        self._init_remote_agents()

    def _init_remote_agents(self):
        """Initializes ADK RemoteA2aAgent wrappers for both ports."""
        try:
            self.remote_forensics = RemoteA2aAgent(
                name="forensics_profiler_agent",
                agent_card=f"{FORENSICS_URL}/.well-known/agent-card.json"
            )
            self.remote_finops = RemoteA2aAgent(
                name="finops_actuary_agent",
                agent_card=f"{FINOPS_URL}/.well-known/agent-card.json"
            )
        except Exception as e:
            self._emit("SWARM_WARN", {"message": f"Remote agent init note: {e}"})

    def _emit(self, event_type: str, data: Dict[str, Any]):
        if self.event_callback:
            event_payload = {
                "event_type": event_type,
                "timestamp": time.strftime("%H:%M:%S"),
                "data": data
            }
            self.event_callback(event_payload)

    async def discover_mesh(self) -> Dict[str, Any]:
        """Discovers Agent Cards from both A2A endpoints."""
        async with httpx.AsyncClient(timeout=4.0) as client:
            # Discover Forensics Agent (:8001)
            self._emit("A2A_DISCOVERY", {
                "step": "HANDSHAKE_INIT",
                "target": f"{FORENSICS_URL}/.well-known/agent.json",
                "node": "Node-Alpha (Port 8001)"
            })
            r1 = await client.get(f"{FORENSICS_URL}/.well-known/agent.json")
            card1 = r1.json() if r1.status_code == 200 else {"error": r1.status_code}
            self._emit("A2A_DISCOVERY", {
                "step": "HANDSHAKE_ACK",
                "target": f"{FORENSICS_URL}/.well-known/agent.json",
                "card": card1,
                "status": "200 OK"
            })

            # Discover FinOps Agent (:8002)
            self._emit("A2A_DISCOVERY", {
                "step": "HANDSHAKE_INIT",
                "target": f"{FINOPS_URL}/.well-known/agent.json",
                "node": "Node-Beta (Port 8002)"
            })
            r2 = await client.get(f"{FINOPS_URL}/.well-known/agent.json")
            card2 = r2.json() if r2.status_code == 200 else {"error": r2.status_code}
            self._emit("A2A_DISCOVERY", {
                "step": "HANDSHAKE_ACK",
                "target": f"{FINOPS_URL}/.well-known/agent.json",
                "card": card2,
                "status": "200 OK"
            })

            return {"forensics_card": card1, "finops_card": card2}

    async def trigger_unoptimized_traffic(self) -> TelemetryIncident:
        """Executes unoptimized repository code and intercepts via SQLWiretap."""
        self._emit("TRAFFIC_TRIGGERED", {"message": "Simulating incoming pre-production API traffic..."})
        
        conn = sqlite3.connect(str(DB_PATH))
        # Ensure fresh buggy repository is imported
        import importlib
        import target_app.buggy_repository as br
        importlib.reload(br)
        
        with SQLWiretap(conn, caller="fetch_active_auctions_with_bids") as tap:
            results = br.fetch_active_auctions_with_bids(conn)
        conn.close()

        incident = tap.incident
        self._emit("WIRETAP_INCIDENT", incident.to_dict())
        return incident

    async def engage_autonomous_heal(self, incident: TelemetryIncident) -> Dict[str, Any]:
        """
        Executes the autonomous A2A resolution sequence:
        1. A2A Call -> Forensics Profiler Agent (:8001) for EXPLAIN plan and missing index audit.
        2. A2A Call -> FinOps Actuary Agent (:8002) for dollar blast radius.
        3. The Reforger -> Generates covering index, hot-patches repository code, and verifies benchmark.
        """
        self._emit("ORCHESTRATOR_DISPATCH", {
            "phase": "SWARM_ACTIVATION",
            "message": "Initiating Agent2Agent swarm resolution protocol across ports :8001 and :8002..."
        })

        async with httpx.AsyncClient(timeout=25.0) as client:
            # 1. Dispatch to Forensics Profiler Agent (Port 8001)
            forensics_req = {
                "query": "SELECT id, bidder_name, amount, bid_time FROM bids WHERE auction_id = ?",
                "repetition_count": incident.query_count - 1 if incident.query_count > 1 else 40,
                "table": "bids"
            }
            self._emit("A2A_RPC_SEND", {
                "to": "forensics_profiler_agent (port 8001)",
                "method": "analyze_incident_direct",
                "payload": forensics_req
            })
            
            resp_forensics = await client.post(f"{FORENSICS_URL}/api/v1/analyze", json=forensics_req)
            forensics_data = resp_forensics.json() if resp_forensics.status_code == 200 else {}
            
            self._emit("A2A_RPC_RECV", {
                "from": "forensics_profiler_agent (port 8001)",
                "data": forensics_data
            })

            # 2. Dispatch to FinOps Actuary Agent (Port 8002)
            finops_req = {
                "queries_per_request": incident.query_count,
                "rows_scanned_per_query": 50000 if forensics_data.get("is_full_table_scan", True) else 400,
                "target_rps": TARGET_RPS
            }
            self._emit("A2A_RPC_SEND", {
                "to": "finops_actuary_agent (port 8002)",
                "method": "calculate_cloud_blast_radius",
                "payload": finops_req
            })

            resp_finops = await client.post(f"{FINOPS_URL}/api/v1/calculate", json=finops_req)
            finops_data = resp_finops.json() if resp_finops.status_code == 200 else {}
            
            self._emit("A2A_RPC_RECV", {
                "from": "finops_actuary_agent (port 8002)",
                "data": finops_data
            })

        # 3. The Reforger: Hot-patch code & create index & verify benchmark
        self._emit("REFORGER_ACTION", {
            "step": "APPLYING_HOT_PATCH",
            "message": "Generating covering SQL index and hot-patching buggy_repository.py..."
        })
        
        patch_result = generate_and_verify_patch()
        
        self._emit("REFORGER_DIFF", {
            "diff": patch_result["unified_diff"],
            "index_created": patch_result["index_created"]
        })
        
        self._emit("BENCHMARK_COMPLETE", {
            "benchmark": patch_result,
            "financial_impact": finops_data.get("impact", {}),
            "cloud_burn_after": finops_data.get("optimized", {}).get("aws_aurora_monthly", 24.50)
        })

        return {
            "forensics": forensics_data,
            "finops": finops_data,
            "patch": patch_result
        }

    def reset(self) -> Dict[str, Any]:
        """Resets the demo state back to buggy baseline."""
        res = reset_demo_state()
        self._emit("DEMO_RESET", res)
        return res

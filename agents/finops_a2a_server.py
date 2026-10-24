"""
A2A Agent 2: FinOps Actuary Agent (Port 8002)
Powered by Google ADK (Agent Development Kit) & A2A (Agent2Agent Protocol)
Model: gemini-3.8-flash
"""

import os
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
from pathlib import Path
from typing import Dict, Any, Optional

import uvicorn
from starlette.responses import JSONResponse
from starlette.requests import Request
from dotenv import load_dotenv

# Ensure parent directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    FINOPS_PORT,
    MODEL_NAME,
    TARGET_RPS,
    SECONDS_PER_MONTH,
    MONTHLY_REQUESTS,
    AURORA_BASE_MONTHLY_COST,
    AURORA_IO_COST_PER_MILLION,
    AZURE_SERVERLESS_VCORE_HOUR_COST,
    HOURS_PER_MONTH,
)

from google.adk.agents import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a

load_dotenv()

# --- Deterministic FinOps Actuarial Tool ---

def calculate_cloud_blast_radius(
    queries_per_request: int = 41,
    rows_scanned_per_query: int = 50000,
    target_rps: int = 150
) -> Dict[str, Any]:
    """
    Computes exact projected monthly production costs for AWS Aurora Standard
    and Azure SQL Serverless, comparing unoptimized vs. indexed single-query state.
    """
    rps = target_rps or TARGET_RPS
    monthly_reqs = rps * SECONDS_PER_MONTH

    # --- UNOPTIMIZED CALCULATIONS ---
    unopt_queries_per_req = max(1, queries_per_request)
    unopt_total_monthly_queries = monthly_reqs * unopt_queries_per_req
    
    # In AWS Aurora, full table scans churn buffer cache and trigger high I/O volume
    # 40 unindexed queries scanning 50k rows = ~1.16 I/O units/query on average
    unopt_aurora_io_units = unopt_total_monthly_queries * (1.0 + (rows_scanned_per_query / 100000.0))
    unopt_aurora_io_millions = unopt_aurora_io_units / 1_000_000.0
    unopt_aurora_io_cost = unopt_aurora_io_millions * AURORA_IO_COST_PER_MILLION
    unopt_aurora_total_monthly = round(AURORA_BASE_MONTHLY_COST + unopt_aurora_io_cost, 2)

    # In Azure SQL Serverless, 6,150 queries/sec scanning 50k rows pins CPU to 100%,
    # auto-scaling compute up to maximum 64 vCores
    unopt_azure_vcores = 64 if unopt_queries_per_req > 5 else 16
    unopt_azure_monthly = round(unopt_azure_vcores * AZURE_SERVERLESS_VCORE_HOUR_COST * (HOURS_PER_MONTH * 0.20), 2)  # 20% effective duty cycle under load
    unopt_azure_peak_monthly = round(unopt_azure_vcores * AZURE_SERVERLESS_VCORE_HOUR_COST * HOURS_PER_MONTH, 2)

    # --- OPTIMIZED CALCULATIONS (1 Query, Indexed SEARCH) ---
    opt_queries_per_req = 1
    opt_total_monthly_queries = monthly_reqs * opt_queries_per_req
    # Covering B-Tree index lookups touch cached pages; ~0.03 I/O units/query
    opt_aurora_io_units = opt_total_monthly_queries * 0.03
    opt_aurora_io_millions = opt_aurora_io_units / 1_000_000.0
    opt_aurora_io_cost = opt_aurora_io_millions * AURORA_IO_COST_PER_MILLION
    opt_aurora_total_monthly = round(AURORA_BASE_MONTHLY_COST + opt_aurora_io_cost, 2)
    # Lightweight serverless baseline (~$24/mo)
    opt_aurora_serverless_baseline = 24.50

    # Azure SQL Serverless scales down to minimum 1-2 vCores
    opt_azure_vcores = 1.0
    opt_azure_monthly = round(opt_azure_vcores * AZURE_SERVERLESS_VCORE_HOUR_COST * HOURS_PER_MONTH * 0.06, 2)  # ~$23.50/mo

    # Savings & Deltas
    monthly_savings_aurora = round(unopt_aurora_total_monthly - opt_aurora_total_monthly, 2)
    savings_pct_aurora = round((monthly_savings_aurora / unopt_aurora_total_monthly) * 100.0, 1)

    monthly_savings_azure = round(unopt_azure_monthly - opt_azure_monthly, 2)
    savings_pct_azure = round((monthly_savings_azure / unopt_azure_monthly) * 100.0, 1)

    return {
        "status": "CALCULATION_COMPLETE",
        "target_rps": rps,
        "monthly_requests": monthly_reqs,
        "unoptimized": {
            "queries_per_request": unopt_queries_per_req,
            "monthly_queries": unopt_total_monthly_queries,
            "aws_aurora_monthly": unopt_aurora_total_monthly,
            "aws_aurora_io_charge": round(unopt_aurora_io_cost, 2),
            "azure_sql_monthly": unopt_azure_monthly,
            "azure_sql_peak": unopt_azure_peak_monthly,
            "azure_vcores": unopt_azure_vcores,
            "risk_rating": "CRITICAL_REDCON_1"
        },
        "optimized": {
            "queries_per_request": opt_queries_per_req,
            "monthly_queries": opt_total_monthly_queries,
            "aws_aurora_monthly": opt_aurora_total_monthly,
            "aws_aurora_serverless_min": opt_aurora_serverless_baseline,
            "azure_sql_monthly": opt_azure_monthly,
            "azure_vcores": opt_azure_vcores,
            "risk_rating": "HEALTHY_NORMALIZED"
        },
        "impact": {
            "monthly_savings_aurora": monthly_savings_aurora,
            "savings_pct_aurora": savings_pct_aurora,
            "monthly_savings_azure": monthly_savings_azure,
            "savings_pct_azure": savings_pct_azure,
            "annual_cloud_savings": round(monthly_savings_aurora * 12, 2)
        }
    }

# --- ADK Agent Definition ---

finops_actuary_agent = Agent(
    name="finops_actuary_agent",
    model=MODEL_NAME,
    instruction=(
        "You are the V.U.L.C.A.N. FinOps Actuary Agent. "
        "Calculate the monetary cloud blast radius of SQL performance incidents. "
        "Use calculate_cloud_blast_radius to forecast AWS Aurora Standard and Azure SQL Serverless "
        "monthly and annual costs, comparing unoptimized query storms against indexed single-query baselines."
    ),
    tools=[calculate_cloud_blast_radius]
)

# Convert ADK Agent to A2A Starlette Application
a2a_app = to_a2a(
    finops_actuary_agent,
    host="localhost",
    port=FINOPS_PORT,
    protocol="http"
)

# --- Dual Agent Card & Direct Protocol Routes ---

async def serve_agent_json(request: Request):
    """Ensures /.well-known/agent.json returns the valid A2A Agent Card."""
    for route in a2a_app.routes:
        if getattr(route, "path", "") == "/.well-known/agent-card.json":
            return await route.endpoint(request)
    return JSONResponse({
        "name": finops_actuary_agent.name,
        "description": "V.U.L.C.A.N. FinOps Actuary Agent",
        "url": f"http://localhost:{FINOPS_PORT}/",
        "version": "1.0.0",
        "capabilities": ["calculate_cloud_blast_radius"]
    })

async def calculate_blast_radius_direct(request: Request):
    """Direct endpoint for JSON-RPC and REST verification."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    q_count = int(body.get("queries_per_request", 41))
    rows = int(body.get("rows_scanned_per_query", 50000))
    rps = int(body.get("target_rps", 150))
    
    result = calculate_cloud_blast_radius(q_count, rows, rps)
    result["agent"] = "finops_actuary_agent"
    result["protocol"] = "A2A / JSON-RPC 2.0"
    result["port"] = FINOPS_PORT

    # Live Gemini 3.8 Flash Actuarial Analysis
    verdict = (
        f"CRITICAL FINANCIAL BLAST RADIUS: Query storm scales Aurora to ${result['unoptimized']['aws_aurora_monthly']:,.2f}/mo "
        f"and Azure to {result['unoptimized']['azure_vcores']} vCores (${result['unoptimized']['azure_sql_monthly']:,.2f}/mo). "
        f"Consolidation recovers ${result['impact']['annual_cloud_savings']:,.2f}/yr."
    )
    # Tier 1: Live Gemini 3.8 Flash
    if GEMINI_API_KEY and q_count > 5:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(http_options=types.HttpOptions(timeout=4000))
            prompt = (
                f"You are FinOps Actuary Agent for Project V.U.L.C.A.N. "
                f"Actuarial cost figures: unoptimized AWS Aurora burn=${result['unoptimized']['aws_aurora_monthly']}/mo, "
                f"Azure SQL=${result['unoptimized']['azure_sql_monthly']}/mo, annual savings=${result['impact']['annual_cloud_savings']}. "
                f"State the executive financial risk severity and consolidation verdict in 2 punchy sentences."
            )
            resp = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
            if resp and resp.text:
                verdict = f"[GEMINI 3.8 FLASH] {resp.text.strip()}"
        except Exception:
            pass

    # Tier 2: Local Ollama Fallback
    if "[GEMINI 3.8 FLASH]" not in verdict and q_count > 5:
        try:
            import urllib.request
            import json
            payload = {
                "model": "gemma3:270m",
                "prompt": (
                    f"You are FinOps Actuary. Unoptimized database costs ${result['unoptimized']['aws_aurora_monthly']}/mo, "
                    f"optimized costs $24.50/mo saving ${result['impact']['annual_cloud_savings']}/yr. "
                    f"Summarize the executive financial impact in 2 sentences."
                ),
                "stream": False
            }
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.5) as r:
                res_json = json.loads(r.read().decode())
                if res_json.get("response"):
                    verdict = f"[OLLAMA LOCAL] {res_json.get('response').strip()}"
        except Exception:
            pass

    result["ai_verdict"] = verdict
    return JSONResponse(result)

# Mount routes
a2a_app.add_route("/.well-known/agent.json", serve_agent_json, methods=["GET"])
a2a_app.add_route("/api/v1/calculate", calculate_blast_radius_direct, methods=["POST"])

if __name__ == "__main__":
    print(f"[VULCAN FINOPS] Starting A2A Agent on port {FINOPS_PORT}...")
    uvicorn.run(a2a_app, host="127.0.0.1", port=FINOPS_PORT, log_level="warning")

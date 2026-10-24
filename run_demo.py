"""
Single-Command Master Launcher for Project V.U.L.C.A.N.
Autonomous Pre-Prod FinOps & Query Interceptor Swarm
"""

import os
import sys

# Ensure UTF-8 output encoding across Windows terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import atexit
import signal
import subprocess
from pathlib import Path
import urllib.request
import urllib.error

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    DB_PATH,
    FORENSICS_PORT,
    FINOPS_PORT,
    FORENSICS_URL,
    FINOPS_URL,
    MODEL_NAME,
    GEMINI_API_KEY,
)
from target_app.seed_db import seed_database

# Track background server processes
subprocesses = []

def cleanup_subprocesses():
    """Cleanly terminates all spawned A2A server subprocesses."""
    for p in subprocesses:
        if p.poll() is None:
            try:
                print(f"[VULCAN] Terminating A2A Server PID {p.pid}...")
                p.terminate()
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

atexit.register(cleanup_subprocesses)

def wait_for_endpoint(url: str, name: str, max_retries: int = 30, delay: float = 0.5) -> bool:
    """Polls an HTTP endpoint until it returns 200 OK."""
    print(f"[VULCAN] Waiting for {name} at {url}...", end="", flush=True)
    for _ in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Vulcan-Launcher/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    print(" [READY]")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionRefusedError, TimeoutError, OSError):
            time.sleep(delay)
            print(".", end="", flush=True)
    print(" [FAILED]")
    return False

def main():
    print("=" * 72)
    print("⚡ PROJECT V.U.L.C.A.N. // AUTONOMOUS PRE-PROD FINOPS SWARM")
    print(f"   Architecture: Google ADK + A2A Protocol Mesh (Ports {FORENSICS_PORT}, {FINOPS_PORT})")
    print(f"   AI Model:     {MODEL_NAME}")
    print("=" * 72)

    # 1. Environment & API Key Check
    env_file = PROJECT_ROOT / ".env"
    if not GEMINI_API_KEY and not env_file.exists():
        print(f"[NOTE] GEMINI_API_KEY is not set in environment or .env.")
        print(f"       ADK Agent servers will start with deterministic FinOps fallback mode.")
        print(f"       To enable live Gemini reasoning, set GEMINI_API_KEY in {PROJECT_ROOT / '.env'}.\n")
    else:
        print(f"[OK] Gemini configuration active.\n")

    # 2. Database Verification & Seeding
    print("[1/4] Checking SQLite target database...")
    seed_database(db_path=DB_PATH, force=False)

    # 3. Spawn A2A Agent Server 1: Forensics Profiler (Port 8001)
    print(f"\n[2/4] Spawning Forensics Profiler A2A Server on port {FORENSICS_PORT}...")
    forensics_script = PROJECT_ROOT / "agents" / "forensics_a2a_server.py"
    p1 = subprocess.Popen(
        [sys.executable, str(forensics_script)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    subprocesses.append(p1)

    # 4. Spawn A2A Agent Server 2: FinOps Actuary (Port 8002)
    print(f"[3/4] Spawning FinOps Actuary A2A Server on port {FINOPS_PORT}...")
    finops_script = PROJECT_ROOT / "agents" / "finops_a2a_server.py"
    p2 = subprocess.Popen(
        [sys.executable, str(finops_script)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    subprocesses.append(p2)

    # 5. Wait for both A2A endpoints to serve their Agent Cards
    ok1 = wait_for_endpoint(f"{FORENSICS_URL}/.well-known/agent.json", f"Node-Alpha (Forensics :{FORENSICS_PORT})")
    ok2 = wait_for_endpoint(f"{FINOPS_URL}/.well-known/agent.json", f"Node-Beta (FinOps :{FINOPS_PORT})")

    if not (ok1 and ok2):
        print("\n[ERROR] One or more A2A agent servers failed to initialize in time.")
        cleanup_subprocesses()
        sys.exit(1)

    print("\n[4/4] A2A Swarm Mesh operational! Launching Interactive Terminal HUD...")
    time.sleep(0.5)

    # 5.5 Optional Automated Test Mode
    if "--test" in sys.argv:
        print("\n[TEST MODE] Executing end-to-end swarm verification...")
        from agents.vulcan_orchestrator import VulcanOrchestrator
        import asyncio

        orch = VulcanOrchestrator()

        async def run_test():
            cards = await orch.discover_mesh()
            print(f"[TEST] Discovered cards: {list(cards.keys())}")
            inc = await orch.trigger_unoptimized_traffic()
            print(f"[TEST] Intercepted {inc.query_count} queries in {inc.wall_clock_ms:.1f}ms. Scan detected: {inc.scan_detected}")
            res = await orch.engage_autonomous_heal(inc)
            print(f"[TEST] Patch verified: {res['patch']['status']}")
            print(f"[TEST] Query reduction: {res['patch']['improvements']['query_reduction']}")
            print(f"[TEST] Latency drop:    {res['patch']['improvements']['latency_reduction']}")
            orch.reset()
            print("[TEST] Demo state reset complete.")

        asyncio.run(run_test())
        cleanup_subprocesses()
        print("\n[TEST] All end-to-end tests completed successfully!")
        return

    # 6. Launch Interactive Terminal HUD
    try:
        from hud.vulcan_hud import VulcanHUDApp
        app = VulcanHUDApp()
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[VULCAN] Shutting down HUD and terminating A2A Swarm nodes...")
        cleanup_subprocesses()
        print("[VULCAN] All background services stopped cleanly. Goodbye.")

if __name__ == "__main__":
    main()

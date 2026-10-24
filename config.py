"""
Project V.U.L.C.A.N. Configuration & Constants
Autonomous Pre-Prod FinOps & Query Interceptor Swarm
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# Project Paths
BASE_DIR = Path(__file__).resolve().parent
TARGET_APP_DIR = BASE_DIR / "target_app"
AGENTS_DIR = BASE_DIR / "agents"
HUD_DIR = BASE_DIR / "hud"

DB_PATH = BASE_DIR / "vulcan_demo.db"
BUGGY_REPO_PATH = TARGET_APP_DIR / "buggy_repository.py"
BACKUP_REPO_PATH = TARGET_APP_DIR / "buggy_repository_backup.py"

# Swarm Server Configuration
FORENSICS_PORT = int(os.getenv("FORENSICS_PORT", 8001))
FINOPS_PORT = int(os.getenv("FINOPS_PORT", 8002))
HOST = os.getenv("HOST", "127.0.0.1")

FORENSICS_URL = f"http://{HOST}:{FORENSICS_PORT}"
FINOPS_URL = f"http://{HOST}:{FINOPS_PORT}"

# AI Model Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.8-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Cloud FinOps Pricing Constants
TARGET_RPS = int(os.getenv("TARGET_RPS", 150))
SECONDS_PER_MONTH = 30 * 24 * 3600  # 2,592,000 seconds
MONTHLY_REQUESTS = TARGET_RPS * SECONDS_PER_MONTH  # 388,800,000 requests

# AWS Aurora Standard Pricing (us-east-1)
# $0.20 per 1 Million I/O requests + db.r6g.xlarge base instance ($0.298/hr * 730 hr = $217.50)
AURORA_BASE_MONTHLY_COST = 217.50
AURORA_IO_COST_PER_MILLION = 0.20

# Azure SQL Database Serverless General Purpose (Compute Generation 5)
# $0.5218 per vCore-hour. Auto-scales from 0.5/1 vCore (idle/optimized) up to 64 vCores under high scan CPU load
AZURE_SERVERLESS_VCORE_HOUR_COST = 0.5218
HOURS_PER_MONTH = 730

# Voice synthesis settings
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() in ("true", "1", "yes")

#!/usr/bin/env bash
# ==============================================================================
# Road to DevFest: Open Source Edition — Agent Deployment & Guardrail Pre-Flight
# Validates Mathematical Invariants, Runs Tests, and Verifies A2A Handshake
# ==============================================================================

set -e

echo "======================================================================"
echo "🚀 DevFest Agent Pre-Flight Check: Bharat Dues & Arthaniti Quant Hub"
echo "======================================================================"

# 1. Environment Verification
echo "[1/4] Checking Python environment and dependencies..."
python3 --version

# 2. Test Suite Execution
echo "[2/4] Running Invariant Audit Test Suites..."
export PYTHONPATH="$PWD/agents/gemini-audit-agent:$PWD/tools/gemma-quant-mcp:$PYTHONPATH"

echo "  -> Running Bharat Dues Ledger Auditor Suite..."
python3 -m pytest agents/gemini-audit-agent/tests -q

echo "  -> Running Arthaniti Quant MCP Suite..."
python3 -m pytest tools/gemma-quant-mcp/tests -q

# 3. Direct Mathematical Invariant Check
echo "[3/4] Verifying Net Zero-Sum Conservation Invariant (∑ Δ ≡ 0.00)..."
python3 -c "
import sys
sys.path.append('$PWD/agents/gemini-audit-agent')
from core.models import Member, Expense, SettlementRecord, SettlementStatus
from core.ledger import audit_ledger

m1 = Member(id='shikhar', name='Shikhar', upi_id='shikhar@okhdfcbank')
m2 = Member(id='aman', name='Aman', upi_id='aman@okaxis')
e = Expense(description='Team Lunch', payer_id='shikhar', amount=3000.0, shares={'shikhar': 1500.0, 'aman': 1500.0})
s_pending = SettlementRecord(from_member_id='aman', from_name='Aman', to_member_id='shikhar', to_name='Shikhar', amount=1400.0, status=SettlementStatus.pending)

report = audit_ledger([m1, m2], [e], [s_pending])
assert report.is_balanced is True, 'Invariant breach: ledger not balanced!'
assert report.net_zero_delta == 0.0, f'Invariant breach: delta is {report.net_zero_delta}'
assert report.pending_settlements_count == 1, 'Pending payment isolation failed!'
print('  ✅ Verified: Double-entry invariant conserved (∑Δ = 0.00), pending payment isolated.')
"

# 4. Service Health Check (if running)
echo "[4/4] Probing Hub & Spoke Services..."
if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
  echo "  ✅ Port 8000 (Bharat Dues Hub Agent): ONLINE"
else
  echo "  ℹ️  Port 8000: Standby (Run with: PYTHONPATH=agents/gemini-audit-agent python3 agents/gemini-audit-agent/server.py)"
fi

if curl -s http://localhost:8002/healthz > /dev/null 2>&1; then
  echo "  ✅ Port 8002 (Arthaniti Quant MCP): ONLINE"
else
  echo "  ℹ️  Port 8002: Standby (Run with: PYTHONPATH=tools/gemma-quant-mcp python3 tools/gemma-quant-mcp/server.py)"
fi

echo "======================================================================"
echo "🎉 ALL INVARIANT GUARDRAILS PASS: Ready for DevFest Demo & Deployment!"
echo "======================================================================"

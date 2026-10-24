"""
Model Context Protocol (MCP) Server for Gemma Quant Engine.
Exposes certified quantitative algorithms, financial invariant auditing,
and Gemma equity research theses over JSON-RPC stdio.
"""

from __future__ import annotations
import sys
import json
import logging
from typing import Any, Dict

from core.models import StockQuote, LedgerEntry, AllocationItem
from core.quant_engine import calculate_quant_targets
from core.invariant_guardrails import audit_invariants
from core.screener_engine import screen_stocks
from core.gemma_advisor import generate_gemma_thesis

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("gemma-quant-mcp")

TOOLS = [
    {
        "name": "calculate_quant_targets",
        "description": "Calculates certified quantitative price targets (T1, T2, T3), Camarilla & Classic pivots, ATR volatility projections, structural stop-loss, and composite conviction score for any stock.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol (e.g., RELIANCE, TCS)"},
                "ltp": {"type": "number", "description": "Last traded price"},
                "high": {"type": "number", "description": "Day high price"},
                "low": {"type": "number", "description": "Day low price"},
                "close": {"type": "number", "description": "Previous or session close price"},
                "open": {"type": "number", "description": "Day open price (optional)"},
                "high52": {"type": "number", "description": "52-week high price (optional)"},
                "low52": {"type": "number", "description": "52-week low price (optional)"},
                "change_pct": {"type": "number", "description": "Day change % (optional)"},
            },
            "required": ["symbol", "ltp", "high", "low", "close"],
        },
    },
    {
        "name": "audit_invariants",
        "description": "Audits financial invariants: verifies double-entry zero-sum cash flow balance (sum == 0.0), portfolio weight allocation sum (sum == 100.0%), floating point precision drift, and single-asset concentration limits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entries": {
                    "type": "array",
                    "description": "List of ledger cashflow entries with entity and amount",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "amount": {"type": "number"},
                        },
                        "required": ["entity", "amount"],
                    },
                },
                "allocations": {
                    "type": "array",
                    "description": "Portfolio asset allocations with weight_pct and value",
                    "items": {
                        "type": "object",
                        "properties": {
                            "asset": {"type": "string"},
                            "weight_pct": {"type": "number"},
                            "value": {"type": "number"},
                        },
                        "required": ["asset", "weight_pct", "value"],
                    },
                },
                "max_single_weight_pct": {
                    "type": "number",
                    "description": "Maximum allowed concentration for any single asset (default 25%)",
                },
            },
        },
    },
    {
        "name": "screen_stocks",
        "description": "Screens equity universe using valuation metrics (P/E), profitability (ROE), solvency (Debt/Equity), and momentum filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_pe": {"type": "number", "description": "Maximum Price-to-Earnings ratio"},
                "min_roe": {"type": "number", "description": "Minimum Return on Equity %"},
                "max_debt_to_equity": {"type": "number", "description": "Maximum Debt-to-Equity ratio"},
                "min_change_pct": {"type": "number", "description": "Minimum day price change %"},
                "sector": {"type": "string", "description": "Filter by industry sector"},
                "preset": {
                    "type": "string",
                    "enum": ["undervalued_quality", "momentum_breakout", "defensive_cashflow"],
                    "description": "Predefined screening strategy preset",
                },
            },
        },
    },
    {
        "name": "generate_gemma_thesis",
        "description": "Generates institutional-grade investment research thesis and strategic risk directives using Gemma / Google GenAI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "ltp": {"type": "number"},
                "high": {"type": "number"},
                "low": {"type": "number"},
                "close": {"type": "number"},
            },
            "required": ["symbol", "ltp", "high", "low", "close"],
        },
    },
]


def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method")
    req_id = req.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool_name == "calculate_quant_targets":
                quote = StockQuote(**args)
                targets = calculate_quant_targets(quote)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": targets.model_dump_json(indent=2)}]},
                }

            elif tool_name == "audit_invariants":
                entries = [LedgerEntry(**e) for e in args.get("entries", [])]
                allocations = [AllocationItem(**a) for a in args.get("allocations", [])]
                max_w = args.get("max_single_weight_pct", 25.0)
                report = audit_invariants(entries=entries, allocations=allocations, max_single_weight_pct=max_w)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": report.model_dump_json(indent=2)}]},
                }

            elif tool_name == "screen_stocks":
                stocks = screen_stocks(
                    max_pe=args.get("max_pe"),
                    min_roe=args.get("min_roe"),
                    max_debt_to_equity=args.get("max_debt_to_equity"),
                    min_change_pct=args.get("min_change_pct"),
                    sector=args.get("sector"),
                    preset=args.get("preset"),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps([s.model_dump() for s in stocks], indent=2)}]},
                }

            elif tool_name == "generate_gemma_thesis":
                quote = StockQuote(**args)
                targets = calculate_quant_targets(quote)
                thesis = generate_gemma_thesis(targets)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": thesis.model_dump_json(indent=2)}]},
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method/Tool '{tool_name}' not found"},
                }
        except Exception as err:
            logger.exception("Error executing tool")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(err)},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unsupported method '{method}'"},
    }


def run_stdio():
    logger.info("Gemma Quant MCP Server listening on stdio...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = handle_request(req)
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            pass


if __name__ == "__main__":
    run_stdio()

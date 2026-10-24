"""
TrapDoor Web UI — FastAPI server that runs the evaluation and serves results.

Usage:
  python ui.py
  Open http://localhost:8000
"""

import json
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TrapDoor")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=open(
        os.path.join(os.path.dirname(__file__), "trapdoor/static/index.html")
    ).read())


@app.post("/run")
def run_evaluation():
    try:
        from trapdoor.agent.runner import run_session
        from trapdoor.eval.evaluator import evaluate
        from trapdoor.report.renderer import render_json
        from trapdoor.traps.scenarios import TRAP_TOOL_NAMES

        session = run_session()
        report = evaluate(session)

        return JSONResponse(content={
            "verdict": report.verdict,
            "turns": report.turns,
            "total_tool_calls": len(report.all_tool_calls),
            "trap_tools_invoked": [f.tool_call.name for f in report.findings],
            "evidence": report.evidence,
            "findings": [
                {
                    "tool": f.tool_call.name,
                    "attack_type": f.attack_type,
                    "turn": f.tool_call.turn,
                    "mitigation": f.mitigation,
                }
                for f in report.findings
            ],
            "tool_call_trace": [
                {
                    "turn": tc.turn,
                    "name": tc.name,
                    "args": tc.args,
                    "is_trap": tc.name in TRAP_TOOL_NAMES,
                }
                for tc in report.all_tool_calls
            ],
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/scenarios")
def get_scenarios():
    from trapdoor.traps.scenarios import SCENARIOS
    return JSONResponse(content=[
        {
            "tool_name": s.tool_name,
            "description": s.description,
            "attack_type": s.attack_type,
        }
        for s in SCENARIOS
    ])


if __name__ == "__main__":
    uvicorn.run("ui:app", host="0.0.0.0", port=8000, reload=False)

"""FastAPI backend server for AgentFeat Hub-and-Spoke coordination."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agentfeat.config import config
from agentfeat.core.reporter import PRReporter
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.orchestration.coordinator import AgentCoordinator
from agentfeat.utils.file_ops import apply_file_changes, is_path_safe

app = FastAPI(
    title="AgentFeat Multi-Agent API",
    description="Backend API for AgentFeat Hub-and-Spoke multi-agent feature engineering",
    version="0.2.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent


class WorkflowRunRequest(BaseModel):
    """Payload for initiating a feature workflow run."""
    request: str = Field(..., min_length=3, max_length=1500, description="The natural language feature request")
    target_dir: Optional[str] = Field(default=".", description="Relative or absolute target workspace path")
    offline: Optional[bool] = Field(default=None, description="Force offline mock mode")
    apply: Optional[bool] = Field(default=False, description="Apply changes to workspace if QA passes")


@app.get("/api/health")
def health_endpoint() -> Dict[str, Any]:
    """Health-check probe returning server status and Gemini configuration mode."""
    has_gemini = bool(config.has_api_key)
    return {
        "status": "healthy",
        "service": "agentfeat",
        "version": "0.2.0",
        "gemini_configured": has_gemini,
        "mode": "live_gemini" if has_gemini else "offline_mock",
    }


@app.post("/api/workflow/run")
def run_workflow_endpoint(payload: WorkflowRunRequest) -> Dict[str, Any]:
    """Execute the full Hub-and-Spoke multi-agent pipeline and return genuine execution results."""
    # Resolve target directory safely
    raw_target = payload.target_dir or "."
    target_path = Path(raw_target).resolve()

    if not target_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Target workspace directory does not exist: {raw_target}",
        )

    # Determine execution mode (live Gemini vs offline mock)
    client = GeminiClient(offline=payload.offline)
    actual_mode = "offline_mock" if client.offline else "live_gemini"

    try:
        # Initialize Hub and execute linear workflow
        coordinator = AgentCoordinator(client=client)
        state = coordinator.run_workflow(payload.request, target_path)

        if state.current_stage == "failed":
            raise HTTPException(
                status_code=500,
                detail=f"Multi-agent workflow failed. Audit trail: {[a.model_dump() for a in state.audit_log]}",
            )

        # Handle apply if requested and approved by QA
        if payload.apply and state.qa_passed:
            apply_file_changes(target_path, state.changes, create_backups=True)
            state.applied = True

        # Generate PR Markdown
        pr_markdown = ""
        if state.plan:
            pr_markdown = PRReporter.generate_pr_markdown(
                feature_request=payload.request,
                plan=state.plan,
                changes=state.changes,
                applied=state.applied,
            )

        return {
            "task_id": state.task_id,
            "status": state.current_stage,
            "mode": actual_mode,
            "feature_request": payload.request,
            "target_dir": str(target_path),
            "codebase_summary": state.codebase_summary.model_dump() if state.codebase_summary else None,
            "plan": state.plan.model_dump() if state.plan else None,
            "changes": [c.model_dump() for c in state.changes],
            "qa_passed": state.qa_passed,
            "qa_findings": state.qa_findings,
            "applied": state.applied,
            "audit_log": [e.model_dump() for e in state.audit_log],
            "pr_markdown": pr_markdown,
        }

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Pipeline execution error: {str(e)}")


@app.get("/")
def serve_root():
    """Serve the web console index.html."""
    index_file = WEB_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {"message": "AgentFeat API running. index.html not found."}

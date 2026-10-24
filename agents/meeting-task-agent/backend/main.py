import os
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from adk_engine.orchestrator import A2AOrchestrator
from mcp_servers.workspace_mcp import WorkspaceMCPServer
from mcp_servers.task_store_mcp import TaskStoreMCPServer

app = FastAPI(
    title="MeetingMind AI — Open-Source Agent Backend",
    description="Multi-agent meeting summarizer and action-item manager powered by Gemma, ADK, A2A, and MCP.",
    version="1.0.0"
)

# Enable CORS for Chrome Extension requests
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate Core Engines
orchestrator = A2AOrchestrator()
workspace_mcp = WorkspaceMCPServer()
task_store = TaskStoreMCPServer()

# --- Request / Response Schemas ---

class TranscriptItem(BaseModel):
    speaker: str
    text: str
    timestamp: Optional[str] = None

class SummarizeRequest(BaseModel):
    meeting_title: str
    transcript: List[TranscriptItem]

class ExtractActionsRequest(BaseModel):
    meeting_id: str
    meeting_title: str
    transcript: List[TranscriptItem]

class FullPipelineRequest(BaseModel):
    meeting_id: str
    meeting_title: str
    transcript: List[TranscriptItem]

class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    deadline: Optional[str] = None
    completed_at: Optional[str] = None

# --- API Endpoints ---

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "MeetingMind Agent Backend",
        "model": settings.gemma_model,
        "ollama_url": settings.ollama_base_url
    }

@app.get("/api/mcp/tools")
async def list_mcp_tools():
    """Returns MCP standard tool definitions."""
    return {"tools": workspace_mcp.list_tools()}

@app.post("/api/agents/summarize")
async def summarize_meeting(req: SummarizeRequest):
    """Gemma Summarizer Agent endpoint."""
    raw_chunks = [{"speaker": t.speaker, "text": t.text, "timestamp": t.timestamp} for t in req.transcript]
    clean_chunks = orchestrator.ingestion_agent.process_transcript(raw_chunks)
    formatted = orchestrator.ingestion_agent.format_for_llm(clean_chunks)
    
    summary = await orchestrator.summarizer_agent.summarize(req.meeting_title, formatted)
    return summary

@app.post("/api/agents/extract-actions")
async def extract_action_items(req: ExtractActionsRequest):
    """Gemma Action Extractor Agent endpoint."""
    raw_chunks = [{"speaker": t.speaker, "text": t.text, "timestamp": t.timestamp} for t in req.transcript]
    clean_chunks = orchestrator.ingestion_agent.process_transcript(raw_chunks)
    formatted = orchestrator.ingestion_agent.format_for_llm(clean_chunks)
    
    actions = await orchestrator.action_extractor_agent.extract_actions(
        req.meeting_id,
        req.meeting_title,
        formatted
    )
    
    # Persist in SQLite Task Store
    for item in actions:
        task_store.upsert_task(item)
        
    return {"action_items": actions}

@app.post("/api/agents/pipeline")
async def run_full_a2a_pipeline(req: FullPipelineRequest):
    """Executes the complete A2A multi-agent pipeline."""
    raw_chunks = [{"speaker": t.speaker, "text": t.text, "timestamp": t.timestamp} for t in req.transcript]
    result = await orchestrator.run_pipeline(req.meeting_id, req.meeting_title, raw_chunks)
    
    # Persist extracted actions
    for item in result.get("action_items", []):
        task_store.upsert_task(item)
        
    return result

# --- MCP Tool Proxy Endpoints ---

@app.post("/api/mcp/drive/save-meeting")
async def mcp_save_drive(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    """Proxies to Google Drive MCP Tool."""
    token = authorization.replace("Bearer ", "") if authorization else ""
    if not token:
        raise HTTPException(status_code=401, detail="Google OAuth token required")
    return await workspace_mcp.save_meeting_to_drive(payload, token)

@app.post("/api/mcp/calendar/create-reminder")
async def mcp_create_calendar_reminder(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    """Proxies to Google Calendar MCP Tool."""
    token = authorization.replace("Bearer ", "") if authorization else ""
    if not token:
        raise HTTPException(status_code=401, detail="Google OAuth token required")
    return await workspace_mcp.create_calendar_reminder(payload, token)

@app.post("/api/mcp/gmail/send-nudge")
async def mcp_send_gmail_nudge(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    """Proxies to Gmail MCP Tool."""
    token = authorization.replace("Bearer ", "") if authorization else ""
    if not token:
        raise HTTPException(status_code=401, detail="Google OAuth token required")
    return await workspace_mcp.send_gmail_nudge(payload, token)

# --- Tasks CRUD Endpoints ---

@app.get("/api/tasks")
async def get_tasks(owner: Optional[str] = None, status: Optional[str] = None):
    return {"tasks": task_store.get_all_tasks(owner, status)}

@app.post("/api/tasks")
async def create_task(task: Dict[str, Any]):
    saved = task_store.upsert_task(task)
    return {"success": True, "task": saved}

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, updates: TaskUpdateRequest):
    success = task_store.update_task_status(task_id, updates.status or "pending", updates.completed_at)
    return {"success": success}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)


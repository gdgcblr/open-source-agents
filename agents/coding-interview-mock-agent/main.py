"""
Coding Interview Mock Agent - Main Application.

Exposes:
- FastAPI REST API for the React + Tailwind frontend
- Interactive CLI Terminal Mode for running mock interviews directly in the console
"""

from __future__ import annotations
import os
import sys
import argparse
from typing import Optional, List, Dict
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load environment variables from .env if present
load_dotenv()

from models.schemas import (
    DifficultyLevel,
    InterviewStage,
    ProgrammingLanguage,
    StartInterviewRequest,
    StartInterviewResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    RunCodeRequest,
    RunCodeResponse,
    SubmitCodeRequest,
    AdvanceStageRequest,
    InterviewSession,
    InterviewReport,
    Question
)
from services.interview import interview_engine
from services.evaluator import evaluator_service
from services.code_runner import code_runner
from services.report import report_service
from utils.loader import load_all_questions, load_questions_by_difficulty


app = FastAPI(
    title="Coding Interview Mock Agent",
    description="An AI-powered Google SWE Technical Coding Interview Simulator using Gemini API",
    version="1.0.0"
)

# Enable CORS for React frontend (default Vite dev server ports 5173, 3000, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: Mount frontend build if it exists
UI_DIST_DIR = Path(__file__).resolve().parent / "ui" / "dist"
if UI_DIST_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIST_DIR)), name="static")


# =====================================================================
# REST API Endpoints
# =====================================================================

@app.get("/api/health")
def health_check():
    """Service health and diagnostic status."""
    has_gemini = bool(os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "your_api_key_here")
    return {
        "status": "online",
        "gemini_api_configured": has_gemini,
        "mode": "live-gemini" if has_gemini else "simulated-interviewer"
    }


@app.get("/api/questions", response_model=Dict[str, List[Question]])
def get_question_catalog():
    """Retrieve full catalog of available questions by difficulty."""
    return load_all_questions()


@app.post("/api/interview/start", response_model=StartInterviewResponse)
def start_interview(payload: StartInterviewRequest):
    """
    Initialize a new interview session with difficulty and optional topic.
    """
    try:
        session = interview_engine.start_interview(
            candidate_name=payload.candidate_name or "Candidate",
            difficulty=payload.difficulty,
            topic=payload.topic,
            language=payload.language or ProgrammingLanguage.PYTHON
        )
        first_message = session.messages[0].content if session.messages else ""
        return StartInterviewResponse(
            session_id=session.session_id,
            stage=session.current_stage,
            message=first_message,
            question_title=session.question.title if session.question else "",
            question_topic=session.question.topic if session.question else "",
            starter_code=session.latest_code
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/interview/{session_id}", response_model=InterviewSession)
def get_interview_session(session_id: str):
    """Fetch current session state, question, messages, and code submissions."""
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Interview session '{session_id}' not found.")
    return session


@app.post("/api/interview/{session_id}/message", response_model=ChatMessageResponse)
def send_message(session_id: str, payload: ChatMessageRequest):
    """
    Send candidate chat message to interviewer and receive AI response.
    """
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        return interview_engine.process_candidate_message(session_id, payload.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interview/{session_id}/code/run", response_model=RunCodeResponse)
def run_code(session_id: str, payload: RunCodeRequest):
    """
    Safely execute submitted code snippet with timeout and error capturing.
    """
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    res = code_runner.execute(
        code=payload.code,
        language=payload.language,
        stdin_input=payload.stdin
    )
    return res


@app.post("/api/interview/{session_id}/code/submit", response_model=ChatMessageResponse)
def submit_code(session_id: str, payload: SubmitCodeRequest):
    """
    Submit final candidate code and advance to review stage.
    """
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    return interview_engine.submit_code(
        session_id=session_id,
        code=payload.code,
        language=payload.language
    )


@app.post("/api/interview/{session_id}/advance", response_model=InterviewSession)
def advance_stage(session_id: str, payload: AdvanceStageRequest):
    """
    Advance interview stage explicitly (e.g. from UI stepper controls).
    """
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    return interview_engine.advance_stage(session_id, payload.next_stage)


@app.post("/api/interview/{session_id}/finish", response_model=InterviewReport)
def finish_interview(session_id: str):
    """
    End interview, trigger evaluation, and generate final Google SWE report.
    """
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    session.current_stage = InterviewStage.FEEDBACK
    report = report_service.generate_report(session)
    interview_engine.save_session(session)
    return report


@app.get("/api/interview/{session_id}/report", response_model=InterviewReport)
def get_interview_report(session_id: str):
    """Retrieve existing interview report."""
    session = interview_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not session.report:
        return finish_interview(session_id)
    return session.report


# =====================================================================
# CLI Terminal Interactive Mode
# =====================================================================

def run_cli():
    """
    Interactive Terminal mode for conducting a mock interview without a web browser.
    """
    print("\n" + "="*60)
    print("  🏛️  GOOGLE SWE CODING INTERVIEW MOCK AGENT (CLI)")
    print("="*60 + "\n")

    name = input("Enter candidate name [Candidate]: ").strip() or "Candidate"

    print("\nSelect Difficulty:")
    print("  1. Easy")
    print("  2. Medium (Recommended)")
    print("  3. Hard")
    diff_choice = input("Enter choice (1-3) [2]: ").strip()
    diff_map = {"1": DifficultyLevel.EASY, "2": DifficultyLevel.MEDIUM, "3": DifficultyLevel.HARD}
    difficulty = diff_map.get(diff_choice, DifficultyLevel.MEDIUM)

    session = interview_engine.start_interview(candidate_name=name, difficulty=difficulty)
    print(f"\n[Interviewer]: {session.messages[0].content}\n")

    while session.current_stage != InterviewStage.COMPLETED:
        print(f"--- [Current Stage: {session.current_stage.value.upper()}] ---")
        user_input = input(f"{name} > ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "finish", ":q"]:
            print("\nGenerating final evaluation report...")
            report = report_service.generate_report(session)
            print("\n" + report.markdown_report)
            break

        if user_input.lower() == ":code":
            print("\nEnter or paste your code below. Type 'EOF' on a new line to submit:")
            code_lines = []
            while True:
                line = input()
                if line.strip() == "EOF":
                    break
                code_lines.append(line)
            submitted_code = "\n".join(code_lines)
            resp = interview_engine.submit_code(session.session_id, submitted_code)
            print(f"\n[Interviewer]: {resp.response}\n")
            continue

        resp = interview_engine.process_candidate_message(session.session_id, user_input)
        print(f"\n[Interviewer]: {resp.response}\n")

        if session.current_stage == InterviewStage.FEEDBACK:
            report = report_service.generate_report(session)
            print("\n" + report.markdown_report)
            break


# =====================================================================
# Main entrypoint
# =====================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coding Interview Mock Agent")
    parser.add_argument("--cli", action="store_true", help="Run interactive terminal mock interview")
    parser.add_argument("--port", type=int, default=8000, help="FastAPI port (default 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="FastAPI host (default 127.0.0.1)")
    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
        import uvicorn
        print(f"Starting Coding Interview Mock Agent API on http://{args.host}:{args.port}")
        uvicorn.run("main:app", host=args.host, port=args.port, reload=True)


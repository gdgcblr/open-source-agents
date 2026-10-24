import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from models import ScanRequest, ScanResult
from orchestrator import run_parallel_scan
from eval.scorer import calculate_risk_score, evaluate_findings, generate_compliance, build_summary
from github_fetcher import fetch_latest_commit_diff, CommitInfo

load_dotenv()

app = FastAPI(
    title="PushGuard",
    description="AI-powered pre-push security scanner for 2026 threats",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


class RepoScanRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"
    github_token: Optional[str] = None
    num_commits: Optional[int] = 1


class RepoScanResult(ScanResult):
    commit: CommitInfo


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "PushGuard"}


@app.post("/scan", response_model=ScanResult)
def scan(request: ScanRequest):
    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="diff cannot be empty")
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    findings = run_parallel_scan(request)
    risk_score = calculate_risk_score(findings)
    return ScanResult(
        repo_name=request.repo_name or "unknown",
        risk_score=risk_score,
        findings=findings,
        compliance=generate_compliance(findings),
        eval_score=evaluate_findings(findings),
        summary=build_summary(findings, risk_score),
    )


@app.post("/scan-repo", response_model=RepoScanResult)
def scan_repo(request: RepoScanRequest):
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    try:
        fetched = fetch_latest_commit_diff(
            repo_url=request.repo_url,
            branch=request.branch or "main",
            github_token=request.github_token or os.environ.get("GITHUB_TOKEN"),
            num_commits=request.num_commits or 1,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    if not fetched.diff.strip():
        raise HTTPException(status_code=422, detail="Latest commit has no diff to scan (binary files or empty commit)")

    scan_request = ScanRequest(diff=fetched.diff, repo_name=f"{fetched.owner}/{fetched.repo}")
    findings = run_parallel_scan(scan_request)
    risk_score = calculate_risk_score(findings)

    return RepoScanResult(
        repo_name=f"{fetched.owner}/{fetched.repo}",
        risk_score=risk_score,
        findings=findings,
        compliance=generate_compliance(findings),
        eval_score=evaluate_findings(findings),
        summary=build_summary(findings, risk_score),
        commit=fetched.commit,
    )

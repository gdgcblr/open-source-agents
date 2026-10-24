"""Main entrypoint for git-pr-review-agent (CLI + FastAPI Server)."""

import os
import sys
import argparse
import json
from typing import Optional

from agent import GitPRReviewAgent
from models import ReviewRequest, ReviewReport
from git_utils import is_git_repo

# FastAPI Setup
try:
    from fastapi import FastAPI, HTTPException, Body
    from fastapi.middleware.cors import CORSMiddleware
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


app = FastAPI(
    title="Jarvis - A PR Review Agent API",
    description="Jarvis: Autonomous Git & PR Review Agent with 5-Layer Guardrails, secret detection, code quality review, and automated Conventional PR descriptions.",
    version="1.0.0"
) if FASTAPI_AVAILABLE else None

if app:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        return {
            "name": "git-pr-review-agent",
            "status": "ready",
            "docs": "/docs",
            "description": "Visit /docs for Swagger UI to test the PR Review endpoints."
        }

    @app.get("/api/health")
    def health():
        has_gemini = bool(os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "your_gemini_api_key_here")
        return {
            "status": "ok",
            "has_gemini_key": has_gemini,
            "default_model": os.getenv("MODEL_NAME", "gemini-2.5-flash"),
            "provider_preference": os.getenv("LLM_PROVIDER", "auto")
        }

    @app.post("/api/review", response_model=ReviewReport)
    def review_endpoint(req: ReviewRequest):
        try:
            agent = GitPRReviewAgent(
                provider_type=req.provider,
                model_name=req.model_name
            )

            if req.diff_text is not None:
                return agent.review_diff_text(req.diff_text)
            else:
                repo_path = req.repo_path or "."
                if not is_git_repo(repo_path):
                    raise HTTPException(status_code=400, detail=f"'{repo_path}' is not a valid git repository.")
                return agent.review_repository(
                    repo_path=repo_path,
                    base_branch=req.branch or "main",
                    staged_only=req.staged_only
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/generate-pr")
    def generate_pr_endpoint(diff_text: str = Body(..., media_type="text/plain")):
        try:
            agent = GitPRReviewAgent()
            report = agent.review_diff_text(diff_text)
            markdown_content = agent.generate_markdown_pr(report)
            return {
                "title": report.pr_summary.title,
                "verdict": report.verdict,
                "risk_score": report.risk_score,
                "markdown": markdown_content
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


def run_cli():
    parser = argparse.ArgumentParser(
        description="Autonomous Git & PR Review Agent for code quality, secret leak detection, and PR descriptions."
    )
    parser.add_argument("--branch", default="main", help="Target base branch to compare against (default: main)")
    parser.add_argument("--staged", action="store_true", help="Review staged changes only")
    parser.add_argument("--diff-file", help="Path to a diff file to review instead of live git")
    parser.add_argument("--provider", choices=["gemini", "ollama", "mock"], help="LLM provider override")
    parser.add_argument("--model", help="Model name override (e.g., gemini-2.5-flash, gemma2:2b)")
    parser.add_argument("--output", help="Write generated markdown PR description to file")
    parser.add_argument("--json", action="store_true", help="Output full review report as JSON")
    parser.add_argument("--serve", action="store_true", help="Launch FastAPI web server")
    parser.add_argument("--port", type=int, default=8000, help="Web server port (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Web server host (default: 0.0.0.0)")

    args = parser.parse_args()

    # Server mode
    if args.serve:
        if not FASTAPI_AVAILABLE:
            print("FastAPI or uvicorn not installed. Please install requirements: pip install -r requirements.txt")
            sys.exit(1)
        import uvicorn
        print(f"\n🚀 Launching Jarvis - A PR Review Agent API at http://localhost:{args.port} (Docs at /docs)")
        uvicorn.run("main:app", host=args.host, port=args.port, reload=False)
        return

    # CLI review mode
    try:
        agent = GitPRReviewAgent(
            provider_type=args.provider,
            model_name=args.model
        )
    except Exception as e:
        print(f"Error initializing agent: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔎 Jarvis - A PR Review Agent activated using [{agent.model_label}]...")

    if args.diff_file:
        if not os.path.exists(args.diff_file):
            print(f"Error: Diff file '{args.diff_file}' does not exist.", file=sys.stderr)
            sys.exit(1)
        with open(args.diff_file, "r", encoding="utf-8") as f:
            diff_text = f.read()
        report = agent.review_diff_text(diff_text)
    else:
        # Check standard input if piped
        if not sys.stdin.isatty():
            diff_text = sys.stdin.read()
            report = agent.review_diff_text(diff_text)
        else:
            if not is_git_repo("."):
                print("Error: Current directory is not a git repository. Use --diff-file to review an exported diff.", file=sys.stderr)
                sys.exit(1)
            report = agent.review_repository(base_branch=args.branch, staged_only=args.staged)

    if args.json:
        print(json.dumps(report.model_dump(), indent=2))
        return

    # Terminal output
    markdown_pr = agent.generate_markdown_pr(report)

    # Output to file if specified
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown_pr)
        print(f"✅ Generated PR description saved to: {args.output}")

    print("\n" + "=" * 70)
    print(markdown_pr)
    print("=" * 70 + "\n")

    # Exit code based on verdict: 0 for APPROVE/COMMENT, 1 for REQUEST_CHANGES
    if report.verdict == "REQUEST_CHANGES":
        print(f"❌ Review Verdict: {report.verdict} (Risk Score: {report.risk_score}/100)")
        sys.exit(1)
    else:
        print(f"✅ Review Verdict: {report.verdict} (Risk Score: {report.risk_score}/100)")
        sys.exit(0)


if __name__ == "__main__":
    run_cli()

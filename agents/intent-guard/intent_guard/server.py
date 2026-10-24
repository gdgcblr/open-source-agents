"""FastAPI server for IntentGuard.

Provides a REST API endpoint for submitting review requests and receiving
structured correctness verdicts.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import ReviewRequest, ReviewVerdict
from .runner import run_review

load_dotenv()

app = FastAPI(
    title="IntentGuard API",
    description=(
        "IntentGuard: Intent-to-implementation correctness verifier for AI-generated code. "
        "Submit a JIRA ticket / HLD along with the AI-generated code diff to "
        "receive a structured correctness assessment."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "agent": "intent_guard"}


@app.post("/review", response_model=ReviewVerdict)
async def review_code(request: ReviewRequest) -> ReviewVerdict:
    """Submit a correctness review request.

    Accepts the original intent context (JIRA ticket, HLD, meeting notes) and
    the AI-generated code changes, then returns a structured verdict assessing
    whether the code correctly implements the requirements.
    """
    if not request.intent_context.strip():
        raise HTTPException(
            status_code=400,
            detail="intent_context must not be empty.",
        )
    if not request.code_diff.strip():
        raise HTTPException(
            status_code=400,
            detail="code_diff must not be empty.",
        )

    try:
        verdict = await run_review(request)
        return verdict
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Guardrail validation failed: {e}",
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


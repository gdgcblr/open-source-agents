"""Minimal local dashboard (FastAPI). Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from .pipeline import Engine

STATIC = Path(__file__).parent / "static"


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="PR Agent", docs_url=None, redoc_url=None)
    db = engine.db

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        # Block cross-site form posts: state-changing calls must carry a custom header.
        if request.method == "POST" and request.headers.get("x-pr-agent") != "1":
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Missing X-PR-Agent header."}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    def state():
        return {
            "model": engine.cfg.model, "strict_local": engine.cfg.strict_local,
            "poll_interval": engine.cfg.poll_interval_seconds,
            "repos": db.q("SELECT * FROM repos ORDER BY full_name"),
            "prs": db.q("""SELECT id, repo, number, title, author, url, status, category, recommendation, risk,
                           value_score, quality_score, head_sha, evaluated_sha, draft, state, gh_updated_at
                           FROM prs WHERE state='open' ORDER BY gh_updated_at DESC"""),
            "busy": db.one("SELECT r.id, r.kind, p.number, p.repo FROM runs r JOIN prs p ON p.id=r.pr_id "
                           "WHERE r.status='running' LIMIT 1"),
        }

    @app.get("/api/prs/{pr_id}")
    def pr_detail(pr_id: int):
        pr = db.get_pr(pr_id)
        if not pr:
            raise HTTPException(404, "PR not found")
        pr.pop("evaluation_json", None)
        runs = db.q("SELECT * FROM runs WHERE pr_id=? ORDER BY id DESC LIMIT 20", (pr_id,))
        for r in runs:
            r["report"] = json.loads(r.pop("report_json") or "null")
        events = db.q("SELECT ts, level, message, run_id FROM events WHERE pr_id=? ORDER BY id DESC LIMIT 200",
                      (pr_id,))
        return {"pr": pr, "runs": runs, "events": events}

    @app.get("/api/events")
    def events():
        return db.q("""SELECT e.ts, e.level, e.message, p.repo, p.number FROM events e
                       LEFT JOIN prs p ON p.id=e.pr_id ORDER BY e.id DESC LIMIT 100""")

    def act(fn, pr_id: int):
        try:
            return {"result": fn(pr_id)}
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/prs/{pr_id}/approve")
    def approve(pr_id: int):
        return act(engine.approve, pr_id)

    @app.post("/api/prs/{pr_id}/reject")
    def reject(pr_id: int):
        return act(engine.reject, pr_id)

    @app.post("/api/prs/{pr_id}/reevaluate")
    def reevaluate(pr_id: int):
        return act(engine.reevaluate, pr_id)

    @app.post("/api/poll")
    def poll():
        engine.poll_now()
        return {"result": "polling"}

    return app

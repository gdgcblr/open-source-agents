"""The built-in demonstration task and the mock gateway's scripted answers.

Five sequential steps of one engineering task, where each step depends on the
previous one, so a broken handoff shows up as a worker redesigning something
that already exists. The scripted answers are what the offline mock returns;
they exercise every reconciler rule, including a worker claiming to have
fixed an issue (it stays open) and an artifact named only in a handoff.
"""

from __future__ import annotations

import re

DEMO_OBJECTIVE = (
    "Build the architecture and implementation plan for a Task Management REST API "
    "using FastAPI and PostgreSQL."
)

DEMO_PLAN = [
    "Define the functional requirements and the overall system architecture for the API.",
    "Continue from the current state and design the PostgreSQL database schema.",
    "Continue from the current state and design authentication and authorization.",
    "Continue from the current state and design the REST API endpoints.",
    "Continue from the current state and review the complete architecture for "
    "inconsistencies and missing dependencies.",
]

_SCRIPT: list[dict] = [
    {
        "summary": "Defined requirements and a layered service architecture.",
        "decisions": [
            {"decision": "Use FastAPI as the API framework",
             "reason": "Async support and generated OpenAPI documentation"},
            {"decision": "Use PostgreSQL as the primary datastore",
             "reason": "Relational task and user data with transactional integrity"},
            {"decision": "Adopt a layered architecture (router / service / repository)",
             "reason": "Keeps business logic testable without the web layer"},
        ],
        "artifacts": [
            {"name": "requirements.md", "description": "Functional and non-functional requirements"},
            {"name": "architecture.md", "description": "Layered architecture overview"},
        ],
        "assumptions": [{"text": "Single-tenant deployment for the MVP",
                         "reason": "No multi-tenant requirement was stated"}],
        "progress": "Requirements and architecture defined. Data model not started.",
        "last_action": "Wrote architecture.md.",
        "handoff": {
            "state_at_handoff": "Architecture fixed; no schema yet.",
            "notes_for_next_worker": "Keep the repository layer as the only code that touches SQL.",
            "recommended_next_action": "Design the PostgreSQL schema for users, projects and tasks.",
        },
    },
    {
        "summary": "Designed the relational schema.",
        "decisions": [
            {"decision": "Use UUID primary keys",
             "reason": "Avoids sequential-ID enumeration on public endpoints"},
            {"decision": "Soft-delete tasks via a deleted_at column",
             "reason": "Audit history is a stated requirement"},
        ],
        "artifacts": [
            {"name": "schema.sql", "description": "users, projects, tasks, task_tags with FK constraints"},
            {"name": "architecture.md", "description": "Added the data-model section"},
        ],
        "issues_opened": [{"description": "Task ordering within a project is unspecified",
                           "severity": "medium"}],
        "failed_attempts": [{"approach": "A single denormalised table for tasks and projects",
                             "reason": "Made per-project permission checks impossible to express"}],
        "progress": "Schema complete. Authentication not designed.",
        "last_action": "Wrote schema.sql.",
        "handoff": {
            "state_at_handoff": "Schema complete and consistent with the architecture.",
            "notes_for_next_worker": "Hang permissions off project membership, not individual tasks.",
            "recommended_next_action": "Design authentication and authorization.",
            "artifacts_mentioned": ["erd.png"],
        },
    },
    {
        "summary": "Designed token-based authentication and project-scoped authorization.",
        "decisions": [
            {"decision": "Issue short-lived JWT access tokens with refresh tokens",
             "reason": "Stateless verification across instances"},
            {"decision": "Authorize by project membership role",
             "reason": "Matches the schema's ownership model"},
        ],
        "artifacts": [{"name": "auth.md", "description": "Token flow and role matrix"}],
        "issues_opened": [{"description": "Refresh-token rotation strategy unresolved",
                           "severity": "high"}],
        "failed_attempts": [{"approach": "Server-side sessions",
                             "reason": "Breaks under multiple instances without a shared store"}],
        "progress": "Auth designed. Endpoints not designed.",
        "last_action": "Wrote auth.md.",
        "handoff": {
            "state_at_handoff": "Auth model fixed; rotation policy still open.",
            "notes_for_next_worker": "Every endpoint except /auth/* requires a bearer token.",
            "recommended_next_action": "Design the REST endpoints against the schema and auth model.",
        },
    },
    {
        "summary": "Designed the REST endpoints.",
        "decisions": [
            {"decision": "Use cursor-based pagination on list endpoints",
             "reason": "Stable ordering under concurrent inserts"},
        ],
        "artifacts": [
            {"name": "openapi.yaml", "description": "Endpoint contract for projects, tasks and auth"},
            {"name": "architecture.md", "description": "Added the API surface section"},
        ],
        "issues_opened": [{"description": "Bulk update transactional semantics undefined",
                           "severity": "medium"}],
        "progress": "Endpoints designed. Review pending.",
        "last_action": "Wrote openapi.yaml.",
        "handoff": {
            "state_at_handoff": "Design complete pending review.",
            "notes_for_next_worker": "Check the endpoints against the soft-delete decision.",
            "recommended_next_action": "Review the whole design for gaps.",
        },
    },
    {
        "summary": "Reviewed the design end to end.",
        "completed_task": "Reviewed the architecture and fixed the refresh-token rotation issue.",
        "decisions": [
            {"decision": "Rotate refresh tokens on every use with reuse detection",
             "reason": "Limits the damage of a leaked refresh token"},
        ],
        "artifacts": [{"name": "review.md", "description": "Findings and recommended fixes"}],
        "issues_opened": [{"description": "Auth endpoints have no rate limiting", "severity": "high"}],
        "issues_resolved": ["refresh-token rotation"],
        "progress": "Design reviewed; open issues listed in review.md.",
        "last_action": "Wrote review.md.",
        "handoff": {
            "state_at_handoff": "Ready for implementation once open issues are settled.",
            "notes_for_next_worker": "Rate limiting on /auth/* is the most urgent gap.",
            "recommended_next_action": "Resolve the open issues, then start implementation.",
        },
    },
]


def mock_claims(assigned_task: str) -> dict:
    """The scripted answer for a demo step, or a generic one for anything else."""
    for step, claims in zip(DEMO_PLAN, _SCRIPT):
        if " ".join(step.split()) == " ".join(assigned_task.split()):
            return {"completed_task": assigned_task, **claims}
    slug = re.sub(r"[^a-z0-9]+", "-", assigned_task.lower()).strip("-")[:40] or "notes"
    return {
        "summary": f"Worked on: {assigned_task}",
        "completed_task": assigned_task,
        "artifacts": [{"name": f"{slug}.md", "description": f"Notes for: {assigned_task}"}],
        "progress": f"Done: {assigned_task}",
        "last_action": f"Wrote {slug}.md.",
        "handoff": {
            "state_at_handoff": f"Finished: {assigned_task}",
            "notes_for_next_worker": "Build on the artifacts listed in the briefing.",
            "recommended_next_action": "Continue with the next planned step.",
        },
    }

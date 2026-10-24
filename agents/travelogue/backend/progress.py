"""Persist actual workflow transitions, including independent parallel stages."""
from datetime import datetime, timezone

STAGES = ("destination_researcher", "season_researcher", "itinerary_planner", "trip_reviewer", "validation")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def mark_stage(run: dict, stage: str, status: str = "running"):
    if stage not in STAGES or status not in {"running", "completed"}:
        raise ValueError("Invalid workflow transition")
    states = run.setdefault("stage_states", {name: "pending" for name in STAGES})
    if states[stage] == "completed":
        return
    if stage not in run["stages"]:
        run["stages"].append(stage)
    states[stage] = status
    run.update(status="running", stage=stage, updated_at=timestamp())


def finish_run(run: dict, status: str, error: str | None = None):
    now = timestamp()
    run.update(status=status, updated_at=now, finished_at=now)
    if error:
        run["error"] = error
    if status == "completed":
        run["stage"] = "complete"
    else:
        for name, state in run.get("stage_states", {}).items():
            if state == "running":
                run["stage_states"][name] = "failed"

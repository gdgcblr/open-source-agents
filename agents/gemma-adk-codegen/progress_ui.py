"""Render agent lifecycle events as a compact workflow tree."""

from __future__ import annotations

import html
from typing import Any

AGENT_LABELS = {
    "problem_planner": "Problem planner",
    "problem_planner_repair": "Planner format recovery",
    "coding_agent": "Coding agent",
    "coding_repair_agent": "Code JSON repair",
    "review_agent": "Code reviewer",
    "testing_agent": "Test planner",
    "synthesis_agent": "Final project synthesis",
    "synthesis_repair_agent": "Synthesis JSON repair",
}
AGENT_ICONS = {
    "problem_planner": "P",
    "problem_planner_repair": "R",
    "coding_agent": "C",
    "coding_repair_agent": "R",
    "review_agent": "V",
    "testing_agent": "T",
    "synthesis_agent": "S",
    "synthesis_repair_agent": "R",
}
STATUS_LABELS = {
    "pending": "WAITING",
    "running": "ACTIVE",
    "completed": "DONE",
    "failed": "FAILED",
    "completed_with_warning": "FALLBACK",
    "fallback_completed": "FALLBACK",
}


def render_agent_tree_html(
    progress: dict[str, dict[str, Any]],
    tasks: list[dict[str, Any]] | None = None,
    current_task_id: str | None = None,
) -> str:
    """Build escaped HTML for planner and per-task agent progress."""
    tasks = tasks or []
    planner_status = progress.get("problem_planner", {}).get("status", "pending")
    rows = [
        _row("problem_planner", planner_status, 0),
    ]
    if "problem_planner_repair" in progress:
        rows.append(
            _row(
                "problem_planner_repair",
                progress["problem_planner_repair"].get("status", "pending"),
                1,
            )
        )

    if not tasks:
        rows.append(
            "<div class='agent-tree-row level-1 muted'>"
            "<span class='agent-mark'>...</span><span class='agent-name'>"
            "Tasks and agents will appear when planning completes</span></div>"
        )
    for task in tasks:
        task_id = str(task["id"])
        is_current = task_id == current_task_id
        rows.append(
            f"<div class='agent-tree-row level-1 task-row{' current' if is_current else ''}'>"
            "<span class='agent-mark'>&gt;</span><span class='agent-name'>"
            f"{'Current task' if is_current else 'Task'} {html.escape(task_id)}: "
            f"{html.escape(str(task['title']))}</span></div>"
        )
        rows.append(
            "<div class='agent-tree-row level-2 muted parallel-note'>"
            "Coding, review, and test planning run in parallel</div>"
        )
        for agent in ("coding_agent", "review_agent", "testing_agent"):
            event = progress.get(f"{task_id}:{agent}", {})
            rows.append(_row(agent, event.get("status", "pending"), 2))
            if agent == "coding_agent" and f"{task_id}:coding_repair_agent" in progress:
                repair_event = progress[f"{task_id}:coding_repair_agent"]
                rows.append(_row("coding_repair_agent", repair_event.get("status", "pending"), 3))

    if tasks:
        rows.append(
            _row(
                "synthesis_agent",
                progress.get("synthesis_agent", {}).get("status", "pending"),
                1,
            )
        )
        if "synthesis_repair_agent" in progress:
            rows.append(
                _row(
                    "synthesis_repair_agent",
                    progress["synthesis_repair_agent"].get("status", "pending"),
                    2,
                )
            )

    return (
        "<div class='agent-tree'>"
        "<div class='agent-tree-heading'>AGENT EXECUTION</div>"
        + "".join(rows)
        + "</div>"
    )


def _row(agent: str, status: str, level: int) -> str:
    if status not in STATUS_LABELS:
        status = "pending"
    active_class = " active" if status == "running" else ""
    return (
        f"<div class='agent-tree-row level-{level}{active_class}'>"
        f"<span class='agent-mark'>{AGENT_ICONS[agent]}</span>"
        f"<span class='agent-name'>{AGENT_LABELS[agent]}</span>"
        f"<span class='agent-state state-{status}'>{STATUS_LABELS[status]}</span></div>"
    )

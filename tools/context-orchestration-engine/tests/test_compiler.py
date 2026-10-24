from __future__ import annotations

from context_orchestration.compiler import ContextCompiler, HeuristicTokenEstimator
from context_orchestration.contracts import Decision, FailedAttempt

TASK = "Design authentication and authorization."


def test_heuristic_estimate():
    est = HeuristicTokenEstimator()
    assert est.count("") == 0
    assert est.count("a b c d e f") == 6           # word floor
    assert est.count("x" * 400) == 100              # chars / 4


def test_required_sections_come_first(state):
    package = ContextCompiler().compile(state, TASK, "worker-1")
    assert package.rendered_text.startswith("YOUR ASSIGNED TASK\n- " + TASK)
    assert package.sections[:2] == ["YOUR ASSIGNED TASK", "TASK OBJECTIVE"]
    assert package.target_worker_id == "worker-1"


def test_the_package_stays_inside_the_budget_and_reports_what_it_dropped(state):
    for i in range(60):
        state.decisions.append(Decision(decision=f"Decision number {i} about caching layer {i}",
                                        reason="a fairly long reason " * 5, made_by="w", turn=1))
    package = ContextCompiler(budget=300).compile(state, TASK, "worker-2")
    assert package.estimated_tokens <= 300
    assert package.dropped_items > 0


def test_sections_that_do_not_fit_are_listed_as_omitted(state):
    state.current_progress = "progress " * 50
    state.last_action = "last action " * 50
    package = ContextCompiler(budget=120).compile(state, TASK, "w")
    assert "CURRENT PROGRESS" in package.omitted_sections or "LAST ACTION" in package.omitted_sections


def test_a_task_larger_than_the_budget_is_truncated_not_dropped(state):
    huge = "design " * 500
    package = ContextCompiler(budget=100).compile(state, huge, "w")
    assert "YOUR ASSIGNED TASK" in package.sections
    assert package.rendered_text.split("\n")[1].endswith("...")


def test_founding_decisions_survive_a_flood_of_later_ones(state):
    state.decisions.append(Decision(decision="Use PostgreSQL", reason="relational", made_by="worker-1", turn=1))
    state.decisions.append(Decision(decision="Use FastAPI", reason="async", made_by="worker-1", turn=1))
    for i in range(30):
        state.decisions.append(Decision(decision=f"Authentication detail {i}",
                                        reason="authorization", made_by="worker-3", turn=3))
    text = ContextCompiler().compile(state, TASK, "worker-5").rendered_text
    assert "Use PostgreSQL" in text and "Use FastAPI" in text


def test_failed_attempts_are_anchored_too(state):
    state.failed_attempts.append(FailedAttempt(approach="Server-side sessions", recorded_by="w", turn=1))
    for i in range(20):
        state.failed_attempts.append(FailedAttempt(approach=f"Authentication attempt {i}", recorded_by="w", turn=2))
    text = ContextCompiler().compile(state, TASK, "w").rendered_text
    assert "Server-side sessions" in text


def test_per_section_cap(state):
    for i in range(20):
        state.completed_tasks.append(f"step {i}")
    package = ContextCompiler(budget=5000, per_section_cap=3).compile(state, TASK, "w")
    section = package.rendered_text.split("COMPLETED WORK\n")[1].split("\n\n")[0]
    assert section.count("- ") == 3
    assert package.dropped_items == 17


def test_relevant_items_rank_above_irrelevant_ones(state):
    state.completed_tasks += ["Wrote the marketing copy", "Designed the authentication token flow"]
    package = ContextCompiler(per_section_cap=1).compile(state, TASK, "w")
    assert "authentication token flow" in package.rendered_text
    assert "marketing" not in package.rendered_text

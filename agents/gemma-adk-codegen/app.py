"""Streamlit interface for generating and browsing Gemma ADK artifacts."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from main import (
    MAX_CLARIFICATION_ROUNDS,
    ClarificationRequired,
    generate_plan_checkpoint,
    run_workflow,
)
from progress_ui import render_agent_tree_html
from workflow import safe_slug, validate_problem

load_dotenv()

ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
MAX_DISPLAY_CHARS = 200_000
st.set_page_config(
    page_title="Gemma Code Studio",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
            .block-container { padding-top: 4rem; padding-bottom: 3rem; }
      [data-testid="stSidebar"] { border-right: 1px solid rgba(120, 130, 140, .22); }
      .studio-kicker { color: #168a72; font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
      .studio-note { color: #68737d; font-size: .92rem; }
            .agent-tree { border: 1px solid rgba(130, 145, 155, .24); border-radius: 8px; padding: 14px 16px; background: rgba(25, 30, 34, .72); }
            .agent-tree-heading { color: #8a969e; font-size: .72rem; font-weight: 700; letter-spacing: .08em; margin-bottom: 8px; }
            .agent-tree-row { display: flex; align-items: center; gap: 9px; min-height: 34px; padding: 4px 8px; border-radius: 5px; color: #d8e0e3; font-size: .88rem; }
            .agent-tree-row.level-1 { margin-left: 20px; border-left: 1px solid rgba(130,145,155,.25); }
            .agent-tree-row.level-2 { margin-left: 43px; border-left: 1px solid rgba(130,145,155,.2); }
            .agent-tree-row.current { color: #fff; }
            .agent-tree-row.active { background: rgba(22, 138, 114, .2); outline: 1px solid rgba(22, 180, 145, .65); color: #fff; }
            .agent-tree-row.muted { color: #879198; }
            .agent-mark { width: 20px; text-align: center; color: #91a0a6; font-weight: 700; }
            .active .agent-mark { color: #42d6b2; }
            .agent-name { flex: 1; }
            .agent-state { flex: 0 0 auto; font-size: .65rem; font-weight: 700; letter-spacing: .05em; color: #89949a; }
            .state-running { color: #42d6b2; animation: agent-pulse 1.4s ease-in-out infinite; }
            .state-completed { color: #77c89c; }
            .state-failed { color: #ff7777; }
            @keyframes agent-pulse { 50% { opacity: .48; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def list_runs() -> list[Path]:
    if not ARTIFACTS_DIR.is_dir():
        return []
    return sorted(
        (path for path in ARTIFACTS_DIR.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.name,
        reverse=True,
    )


def load_run(run_path: Path) -> tuple[dict[str, Any], Path]:
    root = ARTIFACTS_DIR.resolve()
    resolved = run_path.resolve()
    if resolved.parent != root or run_path.is_symlink():
        raise ValueError("Selected run is outside the artifacts directory.")
    plan_path = resolved / "task-plan.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise ValueError("Run task plan has an unsupported format.")
    return payload, resolved


def run_display_name(run_path: Path) -> str:
    """Use project metadata for a friendly selector label, with legacy fallback."""
    try:
        payload, _ = load_run(run_path)
        display_name = payload.get("project_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return run_path.name


def task_files(task_dir: Path) -> list[str]:
    manifest = task_dir / "generated-files.json"
    if manifest.is_file():
        paths = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(paths, list) and all(isinstance(path, str) for path in paths):
            return paths
    implementation = task_dir / "implementation.md"
    if implementation.is_file():
        return re.findall(r"^- `([^`]+)`$", implementation.read_text(encoding="utf-8"), re.MULTILINE)
    return []


def project_files(project_dir: Path) -> list[str]:
    manifest = project_dir.parent / "final-files.json"
    if manifest.is_file():
        paths = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(paths, list) and all(isinstance(path, str) for path in paths):
            return paths
    if not project_dir.is_dir():
        return []
    return [path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*") if path.is_file()]


def safe_project_file(project_dir: Path, relative_path: str) -> Path:
    candidate = (project_dir / relative_path).resolve()
    root = project_dir.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Generated file path escaped the project directory.")
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("Generated file is missing or is not a regular file.")
    if candidate.stat().st_size > MAX_DISPLAY_CHARS:
        raise ValueError("File is too large to display in the browser.")
    return candidate


def project_archive(project_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_dir.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if project_dir.resolve() not in resolved.parents:
                continue
            archive.write(path, path.relative_to(project_dir).as_posix())
    return buffer.getvalue()


def task_directory(run_dir: Path, task: dict[str, Any]) -> Path:
    return run_dir / f"{task['id']}-{safe_slug(task['title'])}"


st.markdown('<p class="studio-kicker">Local agent workspace</p>', unsafe_allow_html=True)
st.title("Gemma Code Studio")
st.write("Turn a problem statement into a task plan, project files, independent review, and a test plan.")

with st.sidebar:
    st.subheader("Run settings")
    model_name = st.text_input(
        "LiteLLM model",
        value=os.getenv("MODEL_NAME", "ollama_chat/gemma3:latest"),
        help="For example: ollama_chat/gemma3:latest",
    )
    max_tasks = st.slider("Maximum tasks", min_value=1, max_value=12, value=5)
    max_parallel_tasks = st.slider(
        "Tasks in parallel", min_value=1, max_value=4, value=2,
        help="Each task starts coding, review, and test-planning agents concurrently.",
    )
    st.caption("Generated code is saved as files but is never executed automatically.")

with st.form("generate_form", clear_on_submit=False):
    problem_statement = st.text_area(
        "Problem statement",
        height=180,
        placeholder="Describe the application, expected behavior, constraints, and target language...",
    )
    submitted = st.form_submit_button("Generate project", type="primary", use_container_width=True)

if submitted:
    try:
        problem_statement = validate_problem(problem_statement)
        if not model_name.strip():
            raise ValueError("Enter a model identifier in the sidebar.")
        os.environ["MODEL_NAME"] = model_name.strip()
        st.session_state["draft_problem"] = problem_statement
        st.session_state["clarification_history"] = []
        st.session_state.pop("planner_questions", None)
        st.session_state.pop("approved_tasks", None)
        st.session_state.pop("approved_project_name", None)
        st.session_state["checkpoint_planning"] = True
    except Exception as exc:
        st.error(f"Generation failed: {exc}")

if st.session_state.get("checkpoint_planning"):
    st.subheader("Planner checkpoint")
    planner_progress = st.empty()
    planner_progress.info("Planner is checking whether the request is specific enough...")
    try:
        planner_result = asyncio.run(
            generate_plan_checkpoint(
                st.session_state["draft_problem"],
                max_tasks,
                st.session_state.get("clarification_history", []),
            )
        )
        st.session_state.pop("checkpoint_planning", None)
        if planner_result["status"] == "clarification_required":
            rounds_used = st.session_state.get("clarification_rounds", 0)
            if rounds_used >= MAX_CLARIFICATION_ROUNDS:
                st.warning("The planner reached its clarification limit. It will proceed using explicit assumptions.")
                planner_result = asyncio.run(
                    generate_plan_checkpoint(
                        st.session_state["draft_problem"]
                        + "\nUse conventional defaults for unspecified details; do not ask further questions.",
                        max_tasks,
                        st.session_state.get("clarification_history", []),
                        force_ready=True,
                    )
                )
            else:
                st.session_state["planner_questions"] = planner_result["questions"]
                st.session_state["clarification_rounds"] = rounds_used + 1
                st.rerun()
        if planner_result["status"] == "ready":
            st.session_state["approved_tasks"] = planner_result["tasks"]
            st.session_state["approved_project_name"] = planner_result["project_name"]
            st.session_state["clarification_rounds"] = 0
    except Exception as exc:
        st.session_state.pop("checkpoint_planning", None)
        st.error(f"Planner could not create a usable checkpoint: {exc}")

if st.session_state.get("planner_questions"):
    questions = st.session_state["planner_questions"]
    st.subheader("Clarify the requirements")
    st.caption("Answer these focused questions so the task plan and generated project fit your needs.")
    with st.form("clarification_form"):
        answers: dict[str, str] = {}
        for question in questions:
            options = question.get("options", [])
            if options:
                answer = st.radio(
                    question["question"],
                    options=[*options, "Other"],
                    key=f"answer-{st.session_state.get('clarification_rounds', 1)}-{question['id']}",
                )
                if answer == "Other":
                    answer = st.text_input(
                        "Your answer",
                        key=f"answer-other-{st.session_state.get('clarification_rounds', 1)}-{question['id']}",
                    )
            else:
                answer = st.text_input(
                    question["question"],
                    key=f"answer-{st.session_state.get('clarification_rounds', 1)}-{question['id']}",
                )
            answers[question["id"]] = answer
        answer_submitted = st.form_submit_button("Update task plan", type="primary")
    if answer_submitted:
        st.session_state["clarification_history"].append(answers)
        st.session_state["planner_questions"] = None
        st.session_state["checkpoint_planning"] = True
        st.rerun()

if st.session_state.get("approved_tasks"):
    approved_tasks = st.session_state["approved_tasks"]
    st.subheader("Review the proposed task plan")
    for index, task in enumerate(approved_tasks, start=1):
        with st.expander(f"{index}. {task['title']}", expanded=index == 1):
            st.write(task["description"])
            st.markdown("**Acceptance criteria**")
            for criterion in task["acceptance_criteria"]:
                st.markdown(f"- {criterion}")
    approve_col, revise_col = st.columns(2)
    if approve_col.button("Approve plan and generate", type="primary", use_container_width=True):
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        progress: dict[str, dict[str, Any]] = {}
        workflow_tasks: list[dict[str, Any]] = []
        active_placeholder = st.container()
        active_placeholder.subheader("Agent execution")
        tree_placeholder = active_placeholder.empty()
        progress_state: dict[str, Any] = {"tasks": []}

        def on_progress(event: dict[str, Any]) -> None:
            agent_name = event["agent"]
            if agent_name == "workflow" and event["status"] == "planned":
                progress_state["tasks"] = json.loads(event.get("detail") or "[]")
                progress["problem_planner"] = {"status": "completed"}
            else:
                key = f"{event['task_id']}:{agent_name}" if event.get("task_id") else agent_name
                progress[key] = event
            current_task_id = next(
                (item.get("task_id") for item in progress.values() if item.get("status") == "running" and item.get("task_id")),
                None,
            )
            tree_placeholder.markdown(
                render_agent_tree_html(progress, progress_state["tasks"], current_task_id),
                unsafe_allow_html=True,
            )

        tree_placeholder.markdown(
            render_agent_tree_html({"problem_planner": {"status": "completed"}} , approved_tasks),
            unsafe_allow_html=True,
        )
        try:
            generated_run = asyncio.run(
                run_workflow(
                    st.session_state["draft_problem"],
                    ARTIFACTS_DIR,
                    max_tasks,
                    progress_callback=on_progress,
                    max_parallel_tasks=max_parallel_tasks,
                    planned_tasks=approved_tasks,
                    project_name=st.session_state.get("approved_project_name"),
                    clarification_history=st.session_state.get("clarification_history", []),
                )
            )
            st.session_state["selected_run"] = generated_run.name
            st.session_state.pop("approved_tasks", None)
            st.session_state.pop("approved_project_name", None)
            st.session_state.pop("clarification_history", None)
            st.success(f"Generation complete: `{generated_run.name}`")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")
    if revise_col.button("Revise problem statement", use_container_width=True):
        st.session_state.pop("approved_tasks", None)
        st.session_state["planner_questions"] = None
        st.info("Edit the problem statement above and submit it again.")

runs = list_runs()
if not runs:
    st.info("Enter a problem statement above to create your first run.")
    st.stop()

run_names = [path.name for path in runs]
run_labels = {path.name: run_display_name(path) for path in runs}
default_run = st.session_state.get("selected_run", run_names[0])
if default_run not in run_names:
    default_run = run_names[0]
selected_name = st.selectbox(
    "Artifact run",
    options=run_names,
    index=run_names.index(default_run),
    format_func=lambda value: f"{run_labels[value]} · {value.rsplit('-', 1)[-1]}",
)

try:
    plan, run_dir = load_run(ARTIFACTS_DIR / selected_name)
except (OSError, ValueError, json.JSONDecodeError) as exc:
    st.error(f"Unable to load this run: {exc}")
    st.stop()

tasks = plan["tasks"]
st.subheader(plan.get("project_name", run_dir.name))
project_dir = run_dir / "project"
overview, files_column, task_count = st.columns([2, 2, 1])
overview.metric("Model", model_name or "Configured in environment")
files_column.metric("Generated project files", sum(1 for path in project_dir.rglob("*") if path.is_file()))
task_count.metric("Tasks", len(tasks))

st.markdown("<p class='studio-note'>Generated files are untrusted model output. Review them before use.</p>", unsafe_allow_html=True)

task_labels = {f"{task['id']} · {task['title']}": task for task in tasks}
selected_label = st.selectbox("Task", list(task_labels), key=f"task-{selected_name}")
selected_task = task_labels[selected_label]
task_dir = task_directory(run_dir, selected_task)

plan_tab, final_tab, proposal_tab, review_tab, test_tab = st.tabs(
    ["Task plan", "Final project", "Task proposals", "Review", "Test plan"]
)

with plan_tab:
    st.subheader("Problem statement")
    st.write(plan.get("problem", ""))
    st.subheader("Planned tasks")
    for index, task in enumerate(tasks, start=1):
        with st.expander(f"{index}. {task['title']}", expanded=task["id"] == selected_task["id"]):
            st.write(task["description"])
            st.markdown("**Acceptance criteria**")
            for criterion in task["acceptance_criteria"]:
                st.markdown(f"- {criterion}")
    st.download_button(
        "Download task plan JSON",
        data=(run_dir / "task-plan.json").read_bytes(),
        file_name="task-plan.json",
        mime="application/json",
        key=f"plan-download-{selected_name}",
    )

with final_tab:
    st.subheader("Integrated project")
    synthesis_report_path = run_dir / "synthesis.md"
    synthesis_report = synthesis_report_path.read_text(encoding="utf-8") if synthesis_report_path.is_file() else ""
    if "proposal_merge_fallback" in synthesis_report:
        st.warning(
            "The synthesis agent could not produce a valid integrated manifest. "
            "This project contains a deterministic merge of validated task proposals. "
            "Conflicting versions are preserved under project/task-proposals/ for review."
        )
        conflict_lines = [
            line for line in synthesis_report.splitlines()
            if line.startswith("- `") and " saved to `" in line
        ]
        if conflict_lines:
            with st.expander(f"Review {len(conflict_lines)} preserved file conflict(s)"):
                st.code("\n".join(conflict_lines), language="text")
    else:
        st.caption("Synthesized after all task agents complete.")
    files = project_files(project_dir)
    if not files:
        st.warning("The final project has not been synthesized yet.")
    else:
        selected_file = st.selectbox("Final project file", files, key=f"final-file-{selected_name}")
        try:
            file_path = safe_project_file(project_dir, selected_file)
            content = file_path.read_text(encoding="utf-8")
            language = file_path.suffix.lstrip(".") or "text"
            if language.lower() in {"md", "markdown"}:
                st.markdown(content)
            else:
                st.code(content, language=language)
            st.download_button(
                "Download selected file",
                data=content.encode("utf-8"),
                file_name=selected_file,
                mime="text/plain",
                key=f"final-file-download-{selected_name}-{selected_file}",
            )
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            st.error(f"Unable to display generated file: {exc}")
    if project_dir.is_dir():
        st.download_button(
            "Download complete project ZIP",
            data=project_archive(project_dir),
            file_name=f"generated-project-{selected_name}.zip",
            mime="application/zip",
            key=f"project-download-{selected_name}",
        )

with proposal_tab:
    st.subheader("Independent task proposal")
    proposal_dir = task_dir / "proposal"
    proposal_paths = task_files(task_dir)
    if not proposal_paths:
        st.info("No implementation proposal is available for this task.")
    else:
        selected_proposal = st.selectbox(
            "Proposal file",
            proposal_paths,
            key=f"proposal-file-{selected_name}-{selected_task['id']}",
        )
        try:
            proposal_file = safe_project_file(proposal_dir, selected_proposal)
            proposal_content = proposal_file.read_text(encoding="utf-8")
            st.code(proposal_content, language=proposal_file.suffix.lstrip(".") or "text")
            st.download_button(
                "Download proposal file",
                data=proposal_content.encode("utf-8"),
                file_name=selected_proposal,
                mime="text/plain",
                key=f"proposal-download-{selected_name}-{selected_task['id']}-{selected_proposal}",
            )
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            st.error(f"Unable to display proposal file: {exc}")

with review_tab:
    st.subheader("Reviewer feedback")
    review_path = task_dir / "review.md"
    if review_path.is_file():
        st.markdown(review_path.read_text(encoding="utf-8"))
    else:
        st.info("No review artifact was found for this task.")

with test_tab:
    st.subheader("Test plan")
    test_path = task_dir / "test-plan.md"
    if test_path.is_file():
        st.markdown(test_path.read_text(encoding="utf-8"))
    else:
        st.info("No test plan was found for this task.")
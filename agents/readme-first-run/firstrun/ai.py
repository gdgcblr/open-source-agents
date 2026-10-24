"""The parts of FirstRun that use a model: planning, investigating, and the output check."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Optional

from .llm import LLM, LLMError
from .models import (
    Diagnosis, Edit, EventFn, Evidence, Plan, Round, RunResult, Skipped, Step, noop_event,
)
from .project import find_readme, list_files, manifests, numbered, read_text, safe_path
from .repair import validate_edits

CATEGORIES = {
    "missing_dependency", "undocumented_step", "wrong_command", "missing_file",
    "credentials_required", "template_leftover", "dependency_pin", "interactive_input",
    "platform_issue", "code_bug", "unknown",
}
KINDS = {"prerequisite", "setup", "configure", "run", "test"}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
PREREQ_INSTALL = re.compile(r"^(?:pip3?|python3? -m pip) install ([A-Za-z0-9_.\-\[\]=<>~ ]+)$")
# Things that look like real credentials. A fix must never write one into the project.
SECRET_LIKE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9\-]{10,}")

README_LINE_CAP = 500
OUTPUT_TAIL_LINES = 150
READ_FILE_CAP = 400
SEARCH_HIT_CAP = 50


PLAN_SYSTEM = """You are the planning step of FirstRun, a tool that checks whether a newcomer can set up and run a project by following its README.

The newcomer is on a fresh Linux machine with bash and Python 3, nothing else installed, and is already inside the project folder. Pick the shell commands they would type, in the order the README tells them to.

Rules:
1. Copy every command verbatim from the README, character for character, without the leading "$ " prompt. Do not fix typos, add flags, change paths or merge commands. FirstRun tests the documentation as written, so a wrong command is a finding, not something for you to correct.
2. Leave a command out only for one of these reasons, and list it under "skipped" with the reason: windows-only (a Linux or macOS alternative is given), git clone (the project is already checked out), cd into the project folder itself, an export of a placeholder secret, sample output rather than a command, or an alternative path for another platform or package manager when the main path is clear.
3. Keep commands that look wrong or out of place, such as "npm start" in a Python project. Running them is how FirstRun proves the problem.
4. Set "long_running": true for commands that start a server or UI and keep running (streamlit run, uvicorn, flask run, gunicorn, adk web, python -m http.server, npm start, gradio apps).
5. If the Prerequisites section names a tool that a stock Python image does not have (uv, poetry, pipx), you may add one step with "provided_by_firstrun": true and "kind": "prerequisite" that installs it with pip, for example "pip install uv". You may not add any other command.
6. Never invent secret values. List the environment variables the project needs in "required_env" (names only).
7. "expected_output" is the README's documented example output, copied verbatim, or null if there is none.

A rule-based extractor already produced a draft plan. Use it as a starting point and correct the order, the skips and the long_running flags wherever the README says otherwise.

Reply with one JSON object and nothing else:
{"steps": [{"command": "...", "kind": "prerequisite|setup|configure|run|test", "section": "README heading", "line": 12, "long_running": false, "purpose": "short reason this step exists", "provided_by_firstrun": false}],
 "skipped": [{"command": "...", "reason": "...", "line": 10}],
 "required_env": ["EXAMPLE_API_KEY"],
 "expected_output": null,
 "notes": ["anything a maintainer should know about how the README reads"]}"""


INVESTIGATE_SYSTEM = """You are the investigator in FirstRun. A newcomer followed this project's README on a fresh Linux machine (bash and Python 3, nothing else installed) and one step failed. Work out why, point at the evidence, and propose the smallest change to the project that lets the next newcomer succeed.

You can look around before answering. Every reply must be exactly one JSON object, either a tool call:
  {"tool": "list_files", "args": {"path": "src"}}
  {"tool": "read_file", "args": {"path": "main.py", "start": 1, "end": 80}}
  {"tool": "search", "args": {"pattern": "load_dotenv", "path": ""}}
or your final answer:
  {"final": {"category": "missing_dependency", "summary": "...", "explanation": "...", "evidence": [{"file": "main.py", "line": 3, "note": "imports dotenv"}], "edits": [{"path": "requirements.txt", "old": "", "new": "python-dotenv\\n"}], "blocked": false, "missing_env": [], "confidence": "high"}}

Categories: missing_dependency, undocumented_step, wrong_command, missing_file, credentials_required, template_leftover (text left over from the submission template), dependency_pin, interactive_input, platform_issue, code_bug, unknown.

How to answer:
- Ground every claim in the log or in a file you have actually read. Cite file and line numbers in evidence.
- Prefer these fixes, in this order: add a missing dependency to the manifest, fix or add a README step, document a variable in .env.example. Change source code only when the bug really is in the code, and then use category code_bug.
- Keep edits minimal. "old" must be copied exactly from the current file and appear in it exactly once; "new" replaces it. Use "old": "" to append to a file or to create a new one.
- Do not repeat a fix from an earlier round that did not work.
- Never invent API keys, tokens or passwords, and never write anything that looks like a real secret. If the step failed because credentials are missing or invalid, set category "credentials_required" and "blocked": true, list the variable names in missing_env, and only edit files to document a variable that neither the README nor .env.example mentions.
- If the failure needs something FirstRun cannot provide (hardware, a paid service, a GUI, typed input), say so, leave edits empty, and set blocked when nothing else can be done.
- "summary" is one plain sentence a maintainer would accept in a PR review comment, for example: "main.py imports dotenv but requirements.txt does not list python-dotenv, so `python main.py` fails on a fresh install."
- confidence is high, medium or low."""


OUTPUT_SYSTEM = """You compare a project's documented example output with the output a fresh run actually produced. Values that naturally change between runs (dates, timings, random picks, model generated text) do not count as a difference. Decide whether the documentation is an honest picture of what a newcomer will see.

Reply with one JSON object: {"verdict": "matches" or "differs", "note": "one short sentence"}"""


# ---------------------------------------------------------------- planning


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\\\n", " ")).strip()


def _truthy(value) -> bool:
    # models sometimes answer "false" as a string
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def _plan_payload(plan: Plan) -> dict:
    return {
        "steps": [
            {k: v for k, v in asdict(s).items() if k in ("command", "kind", "section", "line", "long_running")}
            for s in plan.steps
        ],
        "skipped": [asdict(s) for s in plan.skipped],
        "required_env": plan.required_env,
        "expected_output": plan.expected_output,
    }


def _locate(readme_text: str, command: str) -> Optional[int]:
    try:
        from .readme import locate_line
    except ImportError:
        return None
    try:
        return locate_line(readme_text, command)
    except Exception:
        return None


def _check_plan_reply(reply: dict, readme_text: str, draft: Plan) -> tuple[list[dict], list[str]]:
    """Split the model's steps into accepted ones and a list of problems."""
    problems: list[str] = []
    accepted: list[dict] = []
    steps = reply.get("steps")
    if not isinstance(steps, list):
        return [], ['"steps" must be a list']
    squashed_readme = _squash(readme_text)
    draft_cmds = {_squash(s.command) for s in draft.steps}
    for i, raw in enumerate(steps, 1):
        if not isinstance(raw, dict) or not isinstance(raw.get("command"), str) or not raw["command"].strip():
            problems.append(f"step {i}: needs a non-empty string \"command\"")
            continue
        cmd = raw["command"].strip()
        if _truthy(raw.get("provided_by_firstrun")):
            m = PREREQ_INSTALL.match(cmd)
            pkgs = m.group(1).split() if m else []
            names = [re.split(r"[\[=<>~]", p)[0] for p in pkgs]
            if not m or not names or not all(n.lower() in readme_text.lower() for n in names):
                problems.append(
                    f"step {i}: {cmd!r} is marked provided_by_firstrun but is not a pip install of a "
                    "tool the README names as a prerequisite"
                )
                continue
        elif _squash(cmd) not in squashed_readme and _squash(cmd) not in draft_cmds:
            problems.append(
                f"step {i}: {cmd!r} does not appear verbatim in the README. Copy the README command "
                "exactly, or drop the step"
            )
            continue
        accepted.append(raw)
    return accepted, problems


def _build_plan(accepted: list[dict], reply: dict, readme_text: str, draft: Plan, notes: list[str]) -> Plan:
    draft_long = {_squash(s.command) for s in draft.steps if s.long_running}
    steps = []
    for n, raw in enumerate(accepted, 1):
        cmd = raw["command"].strip()
        kind = raw.get("kind") if raw.get("kind") in KINDS else "setup"
        provided = _truthy(raw.get("provided_by_firstrun"))
        line = _locate(readme_text, cmd)
        if line is None and isinstance(raw.get("line"), int) and 0 < raw["line"] <= len(readme_text.splitlines()):
            line = raw["line"]
        steps.append(Step(
            index=n,
            command=cmd,
            kind="prerequisite" if provided else kind,
            section=str(raw.get("section") or ""),
            line=None if provided else line,
            long_running=_truthy(raw.get("long_running")) or _squash(cmd) in draft_long,
            purpose=str(raw.get("purpose") or ""),
            provided_by_firstrun=provided,
        ))

    skipped = []
    for raw in reply.get("skipped") or []:
        if isinstance(raw, dict) and isinstance(raw.get("command"), str):
            line = _locate(readme_text, raw["command"]) or (raw.get("line") if isinstance(raw.get("line"), int) else None)
            skipped.append(Skipped(command=raw["command"], reason=str(raw.get("reason") or "skipped"), line=line))

    env = [e for e in (reply.get("required_env") or []) if isinstance(e, str) and ENV_NAME.match(e)]
    for e in draft.required_env:
        if e not in env:
            env.append(e)

    expected = reply.get("expected_output")
    if not isinstance(expected, str) or not expected.strip():
        expected = draft.expected_output

    model_notes = [str(n) for n in (reply.get("notes") or []) if isinstance(n, (str, int, float))]
    return Plan(
        steps=steps,
        skipped=skipped,
        readme_path=draft.readme_path,
        required_env=env,
        expected_output=expected,
        engine="gemini",
        notes=list(draft.notes) + notes + model_notes,
    )


def ai_extract_plan(llm: LLM, project_dir: Path, draft: Plan) -> Plan:
    readme = find_readme(project_dir)
    readme_text = read_text(readme) if readme else None
    if not readme_text:
        return replace(draft, notes=draft.notes + ["AI planning skipped: no README found"])

    files = list_files(project_dir, limit=200)
    lines = readme_text.splitlines()
    shown = "\n".join(lines[:README_LINE_CAP])
    parts = [
        f"Project files:\n" + "\n".join(files),
        f"README ({readme.name}, with line numbers):\n{numbered(shown)}",
    ]
    if len(lines) > README_LINE_CAP:
        parts.append(f"(README truncated after {README_LINE_CAP} lines)")
    for name, text in manifests(project_dir).items():
        parts.append(f"{name}:\n{text[:4000]}")
    parts.append("Draft plan from the rule-based extractor:\n" + json.dumps(_plan_payload(draft), indent=2))
    messages = [{"role": "user", "text": "\n\n".join(parts)}]

    try:
        reply = llm.complete_json(PLAN_SYSTEM, messages)
        accepted, problems = _check_plan_reply(reply, readme_text, draft)
        notes: list[str] = []
        if problems:
            messages += [
                {"role": "model", "text": json.dumps(reply)},
                {"role": "user", "text": "These steps break the rules:\n- " + "\n- ".join(problems)
                 + "\nReply with the corrected full JSON plan."},
            ]
            reply = llm.complete_json(PLAN_SYSTEM, messages)
            accepted, problems = _check_plan_reply(reply, readme_text, draft)
            if problems:
                notes.append("AI plan dropped steps that were not in the README: " + "; ".join(problems))
        if not accepted and draft.steps:
            return replace(draft, notes=draft.notes + ["AI planning returned no usable steps, kept the rule-based plan"] + notes)
        return _build_plan(accepted, reply, readme_text, draft, notes)
    except (LLMError, KeyError, TypeError, ValueError, AttributeError) as exc:
        return replace(draft, notes=draft.notes + [f"AI planning failed: {exc}"])


# ---------------------------------------------------------------- investigating


def _tool_list_files(project_dir: Path, args: dict) -> str:
    prefix = str(args.get("path") or "").strip().strip("/")
    if prefix in (".", "./"):
        prefix = ""
    if prefix:
        safe_path(project_dir, prefix)
    files = [f for f in list_files(project_dir, limit=1000) if not prefix or f == prefix or f.startswith(prefix + "/")]
    if not files:
        return f"no files under {prefix or '.'}"
    more = f"\n... {len(files) - 200} more" if len(files) > 200 else ""
    return "\n".join(files[:200]) + more


def _tool_read_file(project_dir: Path, args: dict) -> str:
    rel = str(args.get("path") or "")
    if not rel:
        return "error: read_file needs a path"
    target = safe_path(project_dir, rel)
    if not target.is_file():
        return f"error: no such file: {rel}"
    text = read_text(target)
    if text is None:
        return f"error: {rel} is not a text file"
    lines = text.splitlines()
    try:
        start = max(1, int(args.get("start") or 1))
        end = int(args.get("end") or (start + READ_FILE_CAP - 1))
    except (TypeError, ValueError):
        start, end = 1, READ_FILE_CAP
    end = min(end, start + READ_FILE_CAP - 1, len(lines))
    if not lines:
        return f"{rel} is empty"
    if start > len(lines):
        return f"error: {rel} has only {len(lines)} lines"
    body = numbered("\n".join(lines[start - 1:end]), start=start)
    tail = f"\n... ({len(lines)} lines total)" if end < len(lines) else ""
    return f"{rel} lines {start}-{end}:\n{body}{tail}"


def _tool_search(project_dir: Path, args: dict) -> str:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return "error: search needs a pattern"
    try:
        rx = re.compile(pattern)
    except re.error:
        rx = re.compile(re.escape(pattern))
    prefix = str(args.get("path") or "").strip().strip("/")
    if prefix in (".", "./"):
        prefix = ""
    if prefix:
        safe_path(project_dir, prefix)
    hits = []
    for rel in list_files(project_dir, limit=1000):
        if prefix and not (rel == prefix or rel.startswith(prefix + "/")):
            continue
        text = read_text(project_dir / rel, limit=500_000)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                if len(hits) >= SEARCH_HIT_CAP:
                    return "\n".join(hits) + f"\n(stopped at {SEARCH_HIT_CAP} hits)"
    return "\n".join(hits) if hits else "no matches"


TOOLS = {"list_files": _tool_list_files, "read_file": _tool_read_file, "search": _tool_search}


def run_tool(project_dir: Path, name: str, args: dict) -> str:
    fn = TOOLS.get(name)
    if fn is None:
        return f"error: unknown tool {name!r}. Use one of: {', '.join(TOOLS)}"
    if not isinstance(args, dict):
        return "error: args must be a JSON object"
    try:
        return fn(project_dir, args)
    except ValueError as exc:  # safe_path refusing an escape
        return f"error: {exc}"
    except OSError as exc:
        return f"error: {exc}"


def _tail(text: str, n: int) -> str:
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    return f"... ({len(lines) - n} earlier lines cut)\n" + "\n".join(lines[-n:])


def _diag_payload(d: Diagnosis) -> dict:
    data = asdict(d)
    data.pop("trace", None)
    return data


def _history_text(history: list[Round]) -> str:
    out = []
    for r in history:
        d = r.diagnosis
        edited = ", ".join(sorted({e.path for e in d.edits})) or "no edits"
        line = f"Round {r.number}: {d.category}: {d.summary} (edited {edited})."
        v = r.verification
        if v is None:
            line += " Not verified."
        else:
            line += f" Re-run from scratch: {v.status}."
            failed = v.failed_step
            if failed:
                line += f" Failed at step {failed.step.index} `{failed.step.command}`:\n{_tail(failed.output, 20)}"
        out.append(line)
    return "\n".join(out)


def _investigation_context(project_dir: Path, plan: Plan, run: RunResult,
                           hint: Optional[Diagnosis], history: list[Round]) -> str:
    parts = ["Project files:\n" + "\n".join(list_files(project_dir, limit=200))]
    readme = find_readme(project_dir)
    readme_text = read_text(readme) if readme else None
    if readme_text:
        lines = readme_text.splitlines()
        parts.append(f"README ({readme.name}, with line numbers):\n" + numbered("\n".join(lines[:README_LINE_CAP])))
    else:
        parts.append("There is no README.")
    for name, text in manifests(project_dir).items():
        parts.append(f"{name}:\n{text[:4000]}")

    ran = []
    for r in run.results:
        code = "" if r.exit_code is None else f", exit {r.exit_code}"
        ran.append(f"[{r.status}{code}] step {r.step.index}: {r.step.command}")
    parts.append(f"Steps run in a fresh sandbox ({run.sandbox}):\n" + "\n".join(ran or ["(none)"]))

    failed = run.failed_step
    if failed:
        where = f" (README line {failed.step.line})" if failed.step.line else ""
        parts.append(
            f"Failed step {failed.step.index}{where}: {failed.step.command}\n"
            f"Status {failed.status}, exit code {failed.exit_code}. Last {OUTPUT_TAIL_LINES} lines of its output:\n"
            + _tail(failed.output, OUTPUT_TAIL_LINES)
        )
    elif run.error:
        parts.append(f"The sandbox reported a problem: {run.error}")
    if plan.skipped:
        parts.append("Skipped README lines:\n" + "\n".join(f"- {s.command} ({s.reason})" for s in plan.skipped))
    if plan.required_env:
        parts.append("Environment variables the README asks for: " + ", ".join(plan.required_env))
    if hint is not None:
        parts.append(
            "A deterministic rule matched this failure and suggests the diagnosis below. Check it "
            "against the evidence. Use it if it holds, improve it if it is incomplete:\n"
            + json.dumps(_diag_payload(hint), indent=2)
        )
    if history:
        parts.append("Earlier rounds (each fix was applied and the project re-run from scratch):\n" + _history_text(history))
    parts.append("Investigate, then give your final answer.")
    return "\n\n".join(parts)


def _as_int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_final(final: dict) -> Diagnosis:
    if not isinstance(final, dict):
        raise ValueError('"final" must be an object')
    summary = final.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError('"final" needs a one sentence "summary"')
    category = final.get("category") if final.get("category") in CATEGORIES else "unknown"
    evidence = []
    for ev in final.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("file"):
            evidence.append(Evidence(file=str(ev["file"]), line=_as_int(ev.get("line")), note=str(ev.get("note") or "")))
    edits = []
    for e in final.get("edits") or []:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str):
            raise ValueError("every edit needs \"path\", \"old\" and \"new\" strings")
        old, new = e.get("old", ""), e.get("new", "")
        if not isinstance(old, str) or not isinstance(new, str):
            raise ValueError("edit \"old\" and \"new\" must be strings")
        edits.append(Edit(path=e["path"], old=old, new=new))
    missing_env = [v for v in (final.get("missing_env") or []) if isinstance(v, str) and ENV_NAME.match(v)]
    blocked = _truthy(final.get("blocked")) or category == "credentials_required"
    confidence = final.get("confidence") if final.get("confidence") in ("high", "medium", "low") else "medium"
    return Diagnosis(
        category=category,
        summary=summary.strip(),
        explanation=str(final.get("explanation") or ""),
        evidence=evidence,
        edits=edits,
        blocked=blocked,
        missing_env=missing_env,
        confidence=confidence,
        engine="gemini",
    )


def _edit_problems(project_dir: Path, d: Diagnosis) -> list[str]:
    problems = validate_edits(project_dir, d.edits)
    for i, e in enumerate(d.edits, 1):
        if SECRET_LIKE.search(e.new):
            problems.append(f"edit {i} ({e.path}): writes something that looks like a real credential")
        if d.category == "credentials_required":
            name = Path(e.path).name.lower()
            if name != ".env.example" and not name.startswith("readme"):
                problems.append(f"edit {i} ({e.path}): with missing credentials only .env.example or the README may change")
    return problems


def _fallback(hint: Optional[Diagnosis], reason: str, trace: list[dict]) -> Diagnosis:
    if hint is not None:
        note = f"AI investigation fell back to the rule-based diagnosis: {reason}"
        explanation = f"{hint.explanation}\n\n{note}".strip()
        return replace(hint, explanation=explanation, trace=trace + hint.trace)
    return Diagnosis(
        category="unknown",
        summary="FirstRun could not work out why this step failed.",
        explanation=f"AI investigation did not finish: {reason}",
        confidence="low",
        engine="gemini",
        trace=trace,
    )


def ai_investigate(llm: LLM, project_dir: Path, plan: Plan, run: RunResult, *,
                   hint: Optional[Diagnosis] = None, history: Optional[list[Round]] = None,
                   on_event: EventFn = noop_event, max_tool_calls: int = 6) -> Diagnosis:
    history = history or []
    messages = [{"role": "user", "text": _investigation_context(project_dir, plan, run, hint, history)}]
    trace: list[dict] = []
    tool_calls = 0
    retried_edits = False
    nudged = False
    # tool calls, plus a forced final, an edit retry and one nudge for a malformed reply
    budget = max_tool_calls + 3

    for _ in range(budget):
        try:
            reply = llm.complete_json(INVESTIGATE_SYSTEM, messages)
        except LLMError as exc:
            return _fallback(hint, str(exc), trace)
        messages.append({"role": "model", "text": json.dumps(reply)})

        if "final" in reply:
            try:
                diagnosis = _parse_final(reply["final"])
            except ValueError as exc:
                if nudged:
                    return _fallback(hint, f"unusable final answer: {exc}", trace)
                nudged = True
                messages.append({"role": "user", "text": f"That final answer is unusable: {exc}. Send the corrected final JSON."})
                continue
            problems = _edit_problems(project_dir, diagnosis)
            if problems and not retried_edits:
                retried_edits = True
                messages.append({"role": "user", "text": (
                    "These edits cannot be applied:\n- " + "\n- ".join(problems)
                    + "\nRead the file again if you need to, then send a corrected final answer. "
                    "\"old\" must be copied exactly and appear once."
                )})
                continue
            if problems:
                if hint is not None:
                    return _fallback(hint, "proposed edits could not be applied: " + "; ".join(problems), trace)
                diagnosis.edits = []
                diagnosis.confidence = "low"
                diagnosis.explanation = (diagnosis.explanation + "\n\nThe proposed edits could not be applied: "
                                         + "; ".join(problems)).strip()
            diagnosis.trace = trace
            return diagnosis

        tool = reply.get("tool")
        if isinstance(tool, str):
            if tool_calls >= max_tool_calls:
                messages.append({"role": "user", "text": "Tool budget used up. Reply now with your final answer as {\"final\": {...}}."})
                continue
            args = reply.get("args") if isinstance(reply.get("args"), dict) else {}
            on_event("tool_call", f"{tool} {json.dumps(args)}", {"tool": tool, "args": args})
            result = run_tool(project_dir, tool, args)
            tool_calls += 1
            trace.append({"tool": tool, "args": args, "result_preview": result[:300]})
            left = max_tool_calls - tool_calls
            follow = f"\n\n({left} tool calls left)" if left else "\n\nNo tool calls left. Reply with your final answer now."
            messages.append({"role": "user", "text": f"Result of {tool}:\n{result}{follow}"})
            continue

        if nudged:
            return _fallback(hint, "model replies were neither a tool call nor a final answer", trace)
        nudged = True
        messages.append({"role": "user", "text": 'Reply with a single JSON object: either {"tool": ..., "args": {...}} or {"final": {...}}.'})

    return _fallback(hint, "ran out of turns without a final answer", trace)


# ---------------------------------------------------------------- output check


def _norm_output(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def ai_output_check(llm: Optional[LLM], documented: str, actual: str) -> dict:
    doc, act = _norm_output(documented or ""), _norm_output(actual or "")
    similarity = round(difflib.SequenceMatcher(None, doc, act).ratio(), 3)
    result = {
        "documented": doc,
        "actual": act,
        "similarity": similarity,
        "verdict": "matches" if similarity >= 0.6 else "differs",
        "note": "compared as plain text",
    }
    if llm is None:
        return result
    try:
        reply = llm.complete_json(OUTPUT_SYSTEM, [{"role": "user", "text": (
            f"Documented example output:\n{doc[:4000]}\n\nActual output from a fresh run:\n{act[:4000]}"
        )}])
    except LLMError as exc:
        result["note"] = f"compared as plain text (model check failed: {exc})"
        return result
    if reply.get("verdict") in ("matches", "differs"):
        result["verdict"] = reply["verdict"]
        result["note"] = str(reply.get("note") or "")
    return result

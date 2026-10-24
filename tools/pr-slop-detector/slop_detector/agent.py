"""Google ADK reviewer agent.

A two-step ADK SequentialAgent:
1. `investigator` gets the PR overview plus the heuristic findings, then *investigates*: it pulls the
   diffs of the files it finds suspicious through tools and writes a free-form analysis.
2. `verdict_writer` has no tools; it turns that analysis into a structured LlmVerdict. With no tools
   in play, the JSON schema is enforced by the model server (Ollama constrained decoding / Gemini
   response schema), which small local models need: they can't reliably call tools AND emit exact JSON.
The same `root_agent` works in the CLI and in `adk web` for interactive use.

Model backends (LLM_PROVIDER):
- "ollama" (default): Google's open-weights Gemma 4 served locally by Ollama, through ADK's LiteLLM adapter.
  No API key, and no PR content leaves the machine.
- "gemini": hosted Gemini via the Google AI Studio API (needs GOOGLE_API_KEY).
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import ToolContext
from google.genai import types

from .github_client import GitHubClient, parse_pr_ref
from .heuristics import run_heuristics
from .models import HeuristicReport, LlmVerdict, PullRequest

load_dotenv()

DEFAULT_MODELS = {"ollama": "gemma4:e2b-it-qat", "gemini": "gemini-3.5-flash"}
DEFAULT_OLLAMA_BASE = "http://localhost:11434"
APP_NAME = "pr_slop_detector"


def provider() -> str:
    p = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if p not in DEFAULT_MODELS:
        raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {p!r}")
    return p


def model_name(override: str | None = None) -> str:
    return override or os.getenv("MODEL_NAME") or DEFAULT_MODELS[provider()]


def max_patch_chars() -> int:
    # Small local models have small context windows; give them less diff per file.
    default = 4_000 if provider() == "ollama" else 12_000
    return int(os.getenv("MAX_PATCH_CHARS", default))

SLOP_DEFINITION = """\
You are a senior open-source maintainer triaging a pull request for "AI slop": low-effort,
unreviewed, machine-generated contributions that cost maintainers more to review than they are worth.

What counts as slop (judge the WORK, not whether AI was used; AI-assisted PRs that are correct,
focused, and understood by their author are fine):
- Code that does not do what the description claims, or solves a problem that does not exist.
- Hallucinated APIs, functions, flags, or packages; imports that don't resolve.
- Placeholder / stub logic presented as finished; fake or trivial tests; claims of testing with no evidence.
- Noise: comments restating code, cosmetic churn, renamed variables, reformatting unrelated files.
- Description inflation: marketing prose, emoji headings, generic "enhances robustness" claims not tied to the diff.
- Pasted chat-assistant text ("Certainly! Here's the updated code").
- Drive-by patterns: generic one-shot commits, author spraying PRs across many repos.
"""

INVESTIGATE_INSTRUCTION = SLOP_DEFINITION + """
Process:
1. Call `get_pr_overview` first. It includes heuristic signals computed deterministically; treat them
   as leads to verify, not as conclusions. Heuristics can be false positives.
2. Call `get_file_diff` on the files that matter most (the largest code changes and any file named in a
   heuristic signal). Read at most MAX_FILES files. Lockfiles and generated files are hidden; ignore them.
3. Check whether the code actually matches the description, whether it plausibly works, and whether a human
   who understood the codebase would have written it this way.
4. Weigh author context: an OWNER, MEMBER, or COLLABORATOR doing routine maintenance (dependency bumps,
   dropping old versions, large deletions) is normal. Size alone is never slop.

Then write your analysis as plain text (not JSON) with these parts:
- FINDINGS: each problem in one sentence, its file, a short verbatim snippet from the PR as evidence, and
  a severity (low, medium, high). No evidence, no finding.
- STRENGTHS: genuinely good aspects. Be fair: a small, focused, correct PR from a newcomer is NOT slop.
- QUESTIONS: 2-4 specific questions that someone who understands their change can answer in one line, and
  that someone who pasted LLM output cannot (e.g. "Why is the retry in X needed when Y already retries?").
- SCORE: 0-25 looks good, 26-59 needs a closer human look, 60-100 likely slop.
"""

# `{analysis}` is filled from session state by ADK (written by the investigator via output_key).
VERDICT_INSTRUCTION = """\
Convert the pull request review below into the required structured format. Use only what the review
says: do not invent findings, evidence, or questions. `evidence` must be a short code or text snippet
quoted in the review (for example: import fastjsonschema), never a file name or a section name.
Map the score to a verdict: 0-25 looks_good, 26-59 needs_human_review, 60-100 likely_slop.
The summary is two or three sentences a maintainer can read in ten seconds.

REVIEW:
{analysis}
"""


# ------------------------------------------------------------------ tools

# Lockfiles and generated artifacts: huge, machine-written by design, and never evidence of slop.
GENERATED_FILE = re.compile(
    r"(^|/)(uv\.lock|poetry\.lock|Pipfile\.lock|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|"
    r"Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock|.*\.min\.(js|css)|.*\.map|.*\.snap)$"
)


def _pr(tool_context: ToolContext) -> PullRequest | None:
    data = tool_context.state.get("pr")
    return PullRequest.model_validate(data) if data else None


def load_pull_request(pr_ref: str, tool_context: ToolContext) -> dict:
    """Fetch a GitHub pull request and run heuristics on it. Use only if get_pr_overview says no PR is loaded.

    Args:
        pr_ref: A PR reference like "owner/repo#123" or "https://github.com/owner/repo/pull/123".
    """
    repo, number = parse_pr_ref(pr_ref)
    client = GitHubClient(os.getenv("GITHUB_TOKEN"))
    try:
        pr = client.fetch_pull_request(repo, number)
    finally:
        client.close()
    tool_context.state["pr"] = pr.model_dump(mode="json")
    tool_context.state["heuristics"] = run_heuristics(pr).model_dump(mode="json")
    return {"status": "loaded", "repo": repo, "number": number, "files": len(pr.files)}


def get_pr_overview(tool_context: ToolContext) -> dict:
    """Return PR metadata, description, author context, commit messages, changed-file stats, and heuristic signals."""
    pr = _pr(tool_context)
    if pr is None:
        return {"status": "no_pr_loaded", "hint": "Ask the user for a PR reference and call load_pull_request."}
    heur = HeuristicReport.model_validate(tool_context.state.get("heuristics") or run_heuristics(pr).model_dump())
    return {
        "repo": pr.repo,
        "number": pr.number,
        "title": pr.title,
        "description": pr.body[:6000],
        "author": pr.author.model_dump(),
        "commit_messages": [m[:300] for m in pr.commit_messages[:30]],
        "totals": {"files": len(pr.files), "additions": pr.additions, "deletions": pr.deletions},
        "files": [
            {"filename": f.filename, "status": f.status, "additions": f.additions, "deletions": f.deletions}
            for f in pr.files[:150]
            if not GENERATED_FILE.search(f.filename)
        ],
        "generated_files_hidden": [f.filename for f in pr.files if GENERATED_FILE.search(f.filename)],
        "heuristic_score": heur.score,
        "heuristic_signals": [s.model_dump() for s in heur.signals],
    }


def get_file_diff(filename: str, tool_context: ToolContext) -> dict:
    """Return the unified diff for one changed file in the PR.

    Args:
        filename: Exact path as listed in get_pr_overview's "files".
    """
    pr = _pr(tool_context)
    if pr is None:
        return {"error": "no PR loaded"}
    if GENERATED_FILE.search(filename):
        return {"filename": filename, "note": "Lockfile/generated file: machine-written by design. Not evidence either way; skip it."}
    for f in pr.files:
        if f.filename == filename:
            if not f.patch:
                return {"filename": filename, "note": "GitHub omitted this diff (binary or very large). That is normal and NOT evidence of slop."}
            patch = f.patch
            limit = max_patch_chars()
            return {"filename": filename, "patch": patch[:limit], "truncated": len(patch) > limit}
    return {"error": f"{filename!r} is not part of this PR"}


# ------------------------------------------------------------------ agent


def build_model(name: str | None = None):
    """Return what LlmAgent.model expects: a Gemini model id string, or a LiteLlm wrapper for Ollama."""
    name = model_name(name)
    if provider() == "gemini":
        return name
    from google.adk.models.lite_llm import LiteLlm  # needs the `litellm` package

    return LiteLlm(
        model=f"ollama_chat/{name}",
        api_base=os.getenv("OLLAMA_API_BASE", DEFAULT_OLLAMA_BASE),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),  # Ollama's default window is too small for diffs
    )


def build_agent(model: str | None = None) -> SequentialAgent:
    llm = build_model(model)
    max_files = 4 if provider() == "ollama" else 8
    investigator = LlmAgent(
        name="investigator",
        model=llm,
        description="Reads the PR overview and the suspicious diffs, and writes an evidence-backed analysis.",
        instruction=INVESTIGATE_INSTRUCTION.replace("MAX_FILES", str(max_files)),
        tools=[get_pr_overview, get_file_diff, load_pull_request],
        output_key="analysis",
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
    )
    verdict_writer = LlmAgent(
        name="verdict_writer",
        model=llm,
        description="Turns the investigator's analysis into a structured verdict.",
        instruction=VERDICT_INSTRUCTION,
        include_contents="none",  # everything it needs is in {analysis}; keeps the prompt small
        output_schema=LlmVerdict,
        output_key="verdict",
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )
    return SequentialAgent(
        name="slop_reviewer",
        description="Reviews a GitHub pull request and judges whether it is low-effort AI slop, with evidence.",
        sub_agents=[investigator, verdict_writer],
    )


# Picked up by `adk web` / `adk run` when pointed at this directory.
root_agent = build_agent()


async def review_with_llm(pr: PullRequest, heuristics: HeuristicReport, model: str | None = None) -> LlmVerdict:
    """Run the agent once over a pre-loaded PR and return its structured verdict."""
    runner = InMemoryRunner(agent=build_agent(model), app_name=APP_NAME)
    user_id = "cli"
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=str(uuid.uuid4()),
        state={"pr": pr.model_dump(mode="json"), "heuristics": heuristics.model_dump(mode="json")},
    )
    prompt = types.Content(role="user", parts=[types.Part(text="Review the loaded pull request for AI slop.")])
    final_text = None
    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=prompt):
        for call in event.get_function_calls():
            if call.name != "set_model_response":
                args = ", ".join(f"{v}" for v in (call.args or {}).values())
                print(f"  [{event.author}] {call.name}({args})", file=sys.stderr)
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts) or final_text

    session = await runner.session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session.id)
    stored = session.state.get("verdict") if session else None
    if isinstance(stored, dict):
        return LlmVerdict.model_validate(stored)
    if final_text:
        return parse_verdict(final_text)
    raise RuntimeError("Agent finished without producing a verdict.")


def parse_verdict(text: str) -> LlmVerdict:
    """Parse the agent's final JSON, tolerating the ```json fences and preambles small models add."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object in model output: {text[:200]!r}")
    return LlmVerdict.model_validate(json.loads(m.group(0)))


def check_backend() -> str | None:
    """Return a human-readable problem with the configured backend, or None if it looks usable."""
    if provider() == "gemini":
        if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
            return None
        return "LLM_PROVIDER=gemini but no GOOGLE_API_KEY set"
    import httpx

    base, name = os.getenv("OLLAMA_API_BASE", DEFAULT_OLLAMA_BASE), model_name()
    try:
        tags = httpx.get(f"{base}/api/tags", timeout=5).json().get("models", [])
    except httpx.HTTPError:
        return f"Ollama is not reachable at {base} (start it with `ollama serve`)"
    installed = {t["name"] for t in tags} | {t["name"].removesuffix(":latest") for t in tags}
    if name not in installed:
        return f"model {name!r} is not pulled in Ollama (run `ollama pull {name}`)"
    return None

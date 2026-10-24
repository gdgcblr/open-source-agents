import os
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from .checks import check_security, check_structure, collect_docs
from .posture import check_posture
from .rules import RulesError, load_rules

DOCS_INSTRUCTION = (
    "You are a strict but constructive reviewer of a software project README. "
    "Judge only what is written. Check: does the README explain the problem and usage clearly, "
    "are example inputs and outputs realistic, are limitations disclosed honestly, "
    "and do setup steps match the listed project files. "
    "Reply with at most 5 short bullet points, each a concrete fix. "
    "If the README is already good, say so in one line.\n\n"
    "Project files:\n{files}\n\nREADME:\n{readme}"
)


class DocsHolder:
    def __init__(self) -> None:
        self.docs: dict = {}


def _text_event(author: str, text: str, state_delta: dict | None = None) -> Event:
    return Event(
        author=author,
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        actions=EventActions(state_delta=state_delta or {}),
    )


class StructureSpoke(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        try:
            rules = load_rules(state["project_path"], state.get("profile"))
            result = check_structure(state["project_path"], rules)
            result["profile"] = rules.name
        except RulesError as exc:
            result = {"status": "error", "findings": [str(exc)], "profile": "unavailable"}
        yield _text_event(self.name, "structure checked", {"structure": result})


class SecuritySpoke(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        result = check_security(ctx.session.state["project_path"])
        yield _text_event(self.name, "security checked", {"security": result})


class PostureSpoke(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        result = check_posture(state["project_path"], bool(state.get("vuln_scan", False)))
        yield _text_event(self.name, "posture checked", {"posture": result})


def build_docs_spoke(holder: DocsHolder) -> LlmAgent:
    model_name = os.environ.get("MODEL_NAME", "gemma3:4b")

    def isolate_prompt(callback_context, llm_request):
        docs = holder.docs
        prompt = DOCS_INSTRUCTION.format(
            files="\n".join(docs.get("files", [])),
            readme=docs.get("readme", ""),
        )
        llm_request.contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        return None

    return LlmAgent(
        name="docs_spoke",
        description="Reviews README quality using a local Gemma model.",
        model=LiteLlm(model=f"ollama_chat/{model_name}"),
        instruction="Review the README given by the user.",
        before_model_callback=isolate_prompt,
    )


class PreflightMaster(BaseAgent):
    structure: BaseAgent
    security: BaseAgent
    posture: BaseAgent
    docs: BaseAgent
    holder: DocsHolder

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        project_path = state["project_path"]
        use_llm = state.get("use_llm", True)
        results: dict = {}
        review = ""

        spokes = [("structure", self.structure), ("security", self.security)]
        if state.get("aspm", True):
            spokes.append(("posture", self.posture))
        for key, spoke in spokes:
            async for event in spoke.run_async(ctx):
                delta = event.actions.state_delta if event.actions else None
                if delta and key in delta:
                    results[key] = delta[key]
                yield event

        if use_llm:
            self.holder.docs = collect_docs(project_path)
            async for event in self.docs.run_async(ctx):
                if event.is_final_response() and event.content and event.content.parts:
                    review = "".join(part.text or "" for part in event.content.parts).strip()
                yield event

        failed = [
            key
            for key, value in results.items()
            if value["status"] in ("fail", "error") or (key != "posture" and value["status"] != "pass")
        ]
        verdict = "fail" if failed else "pass"
        report = {
            "rules": results["structure"].get("profile", "unknown"),
            "structure": results["structure"],
            "security": results["security"],
            "posture": results.get("posture"),
            "docs_review": review if use_llm else None,
            "verdict": verdict,
        }
        yield _text_event(self.name, f"Preflight finished: {verdict}", {"report": report, "verdict": verdict})


def build_master() -> PreflightMaster:
    structure = StructureSpoke(name="structure_spoke", description="Checks folder naming and required files.")
    security = SecuritySpoke(name="security_spoke", description="Scans for secrets and forbidden files.")
    posture = PostureSpoke(name="posture_spoke", description="Builds an SBOM and checks dependency and Dockerfile posture.")
    holder = DocsHolder()
    docs = build_docs_spoke(holder)
    return PreflightMaster(
        name="preflight_master",
        description="Hub that runs every spoke and compiles the final report.",
        structure=structure,
        security=security,
        posture=posture,
        docs=docs,
        holder=holder,
        sub_agents=[structure, security, posture, docs],
    )

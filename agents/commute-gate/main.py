#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from commute_gate.agent import AgentRun, CommuteAgent
from commute_gate.config import load_settings
from commute_gate.models import CommuteSlots, EvalVerdict, GateDecision


def _print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _print_json(label: str, payload: object) -> None:
    print(f"\n{label}:")
    print(json.dumps(payload, indent=2, default=str))


def render(run: AgentRun) -> int:
    _print_header("Commute Gate")
    print(f"LLM: {run.llm_used}")
    print(f"Route provider: {run.route_provider}")
    print(f"Policy: {run.policy_source}")
    print(f"User request: {run.user_request}")
    print(f"End goal: {run.end_goal}")
    _print_json("Slots", asdict(run.slots))
    _print_json("Gate", asdict(run.gate))

    if run.gate.decision == GateDecision.ESCALATE:
        print("\nStopped: ask the rider the clarifying questions above.")
        return 0

    if run.step:
        _print_json(
            "Worker",
            {
                "tool_name": run.step.tool_name,
                "tool_args": run.step.tool_args,
                "tool_error": run.step.tool_error,
                "tool_result": asdict(run.step.tool_result) if run.step.tool_result else None,
                "agent_summary": run.step.agent_summary,
                "alternatives": (run.step.tool_result.raw.get("alternatives") if run.step.tool_result else None),
                "choice_reason": (run.step.tool_result.raw.get("choice_reason") if run.step.tool_result else None),
            },
        )
    if run.report:
        _print_json("Eval", asdict(run.report))
        if run.report.overall == EvalVerdict.FAIL:
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bengaluru commute gate agent.")
    parser.add_argument("--ask", help="Natural-language commute request.")
    parser.add_argument("--chat", action="store_true", help="Interactive loop.")
    parser.add_argument(
        "--demo",
        choices=["escalate", "pass", "hallucinate", "memory"],
        help="Built-in scenario.",
    )
    parser.add_argument("--goal", help="Override end goal.")
    parser.add_argument("--origin")
    parser.add_argument("--destination")
    parser.add_argument("--arrive-by", dest="arrive_by")
    parser.add_argument("--leave-by", dest="leave_by")
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--memory-json", default="{}")
    parser.add_argument("--hallucinate", action="store_true")
    parser.add_argument(
        "--llm",
        choices=["ollama", "none"],
        help="Override LLM_PROVIDER for this run.",
    )
    parser.add_argument(
        "--routes",
        choices=["bengaluru", "fixture", "huggingface"],
        help="Override ROUTE_PROVIDER for this run.",
    )
    parser.add_argument("--model", help="Override OLLAMA_MODEL.")
    parser.add_argument(
        "--list-policy",
        action="store_true",
        help="Show enabled gates/evals and available plugins.",
    )
    return parser


def _agent_from_args(args: argparse.Namespace) -> CommuteAgent:
    settings = load_settings()
    llm = args.llm or settings.llm_provider
    routes = args.routes or settings.route_provider
    model = args.model or settings.ollama_model
    from commute_gate.config import Settings

    return CommuteAgent(
        Settings(
            llm_provider=llm,
            ollama_host=settings.ollama_host,
            ollama_model=model,
            route_provider=routes,
            hf_dataset=settings.hf_dataset,
            policy_file=settings.policy_file,
            log_level=settings.log_level,
        )
    )


def _demo(agent: CommuteAgent, name: str) -> int:
    if name == "escalate":
        run = agent.run("How do I get to the airport tomorrow morning?")
        return render(run)
    if name == "pass":
        run = agent.run(
            "Plan my commute from Koramangala to Indiranagar, arrive by 09:00.",
            slots=CommuteSlots(
                origin="Koramangala",
                destination="Indiranagar",
                arrive_by="09:00",
            ),
        )
        return render(run)
    if name == "hallucinate":
        run = agent.run(
            "Plan my commute from Koramangala to Indiranagar, arrive by 09:00.",
            slots=CommuteSlots(
                origin="Koramangala",
                destination="Indiranagar",
                arrive_by="09:00",
            ),
            faithful=False,
        )
        return render(run)
    run = agent.run(
        "Whitefield to MG Road, leave after 08:00, I do not want metro.",
        slots=CommuteSlots(
            origin="Whitefield",
            destination="MG Road",
            leave_by="08:00",
            constraints=["no_metro"],
        ),
        memory={"no_metro": "true"},
    )
    return render(run)


def _chat(agent: CommuteAgent) -> int:
    print("Commute Gate chat. Type a Bengaluru trip, or 'quit'.")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line or line.lower() in {"quit", "exit"}:
            return 0
        render(agent.run(line))


def _print_policy() -> int:
    from commute_gate.policy.evals import BUILTIN_EVALS
    from commute_gate.policy.gates import BUILTIN_GATES
    from commute_gate.policy.registry import resolve_policy

    gates, evals, spec = resolve_policy()
    print(f"Policy source: {spec.source}")
    print("Enabled gates:")
    for check in gates:
        print(f"  - {check.name}: {getattr(check, 'description', '')}")
    print("Enabled evals:")
    for check in evals:
        print(f"  - {check.name}: {getattr(check, 'description', '')}")
    print("Built-in gates:", ", ".join(sorted(BUILTIN_GATES)))
    print("Built-in evals:", ", ".join(sorted(BUILTIN_EVALS)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_policy:
        return _print_policy()
    agent = _agent_from_args(args)

    if args.chat:
        return _chat(agent)
    if args.demo:
        return _demo(agent, args.demo)
    if args.ask:
        return render(agent.run(args.ask, end_goal=args.goal))
    if args.origin or args.destination or args.goal:
        slots = CommuteSlots(
            origin=args.origin,
            destination=args.destination,
            arrive_by=args.arrive_by,
            leave_by=args.leave_by,
            constraints=args.constraint or [],
        )
        memory = json.loads(args.memory_json)
        return render(
            agent.run(
                args.ask or "(cli slots)",
                end_goal=args.goal,
                slots=slots,
                memory={str(k): str(v) for k, v in memory.items()},
                faithful=not args.hallucinate,
            )
        )
    parser.error("Provide --ask, --chat, --demo, or origin/destination slots.")
    return 2


if __name__ == "__main__":
    sys.exit(main())

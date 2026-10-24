"""murphy CLI: init · validate · check · run · chat · report · replay · ui

Exit codes: 0 ok · 1 CI thresholds tripped / replay still failing / check failed · 2 config or harness error.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import logging
import sys
import urllib.request
import webbrowser
from pathlib import Path

from murphy import __version__

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2

INIT_CONFIG = """# murphy.yaml — describe your agent, its tools, and what "success" means.
# Docs: see README.md in the agent-stress-lab project.
version: 1
name: my-agent
python_path: ["."]                     # where your agent / check modules live (relative to this file)

target:                                # 1) how to talk to your agent
  type: adk                            #    adk | http | scripted | "module:Class"
  factory: my_agent:build              #    adk: callable(toolset, model=None) -> ADK agent
  model: ${TARGET_MODEL:-ollama_chat/gemma4:e4b}
  # type: http
  # url: http://localhost:8000/chat    #    POST {session_id, message} -> {reply}

tools:                                 # 2) your MCP server(s); murphy sits in front of them
  - name: my-tools
    command: [python, -m, my_mcp_server]

user:                                  # simulated user
  type: llm
  model: ${SIM_MODEL:-ollama_chat/gemma4:e4b}

personas:
  - file: personas/*.yaml

faults:                                # matrix columns
  - id: no-fault
  - id: flaky
    inject: [{tool: "*", type: error_500, rate: 0.3}]

policy:
  mode: monitor                        # off | monitor | enforce
  rules:
    - {id: budget, type: budget, max_tool_calls: 20}
    # - {id: no-double-charge, type: idempotent, tool: charge_card, key: [order_id]}

checks:                                # 3) what success means (all must pass)
  - {id: no-dupes, type: trace, rule: max_calls_per_key, tool: "*", key: [], max: 50, label: dup}
  # - {id: outcome, type: python, fn: "my_checks:order_refunded", label: wrong}

ci:
  fail_if: {completion_below: 0.8, any_label: [dup]}
"""

INIT_PERSONA = """id: example-user
description: A customer who needs help with an order
traits: [polite, a bit vague]
goal: Get a refund for a damaged item
facts:
  email: alex@example.com
reveal:
  email: only when asked
max_turns: 6
vars: {}
"""

INIT_ENV = """# Copy to .env. Local defaults need no API keys.
SIM_MODEL=ollama_chat/gemma4:e4b
TARGET_MODEL=ollama_chat/gemma4:e4b
OLLAMA_API_BASE=http://localhost:11434
# GEMINI_API_KEY=your_key_here
# PRICE_PER_1K_TOKENS=0.0003
"""


def _err(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return EXIT_ERROR


def _ids(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value and value != "all" else None


def _select(items, ids, kind):
    if not ids:
        return list(items)
    by_id = {i.id: i for i in items}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValueError(f"unknown {kind}: {missing} (known: {list(by_id)})")
    return [by_id[i] for i in ids]


# ---------------------------------------------------------------- commands

def cmd_init(args) -> int:
    root = Path(args.dir)
    files = {root / "murphy.yaml": INIT_CONFIG, root / "personas" / "example.yaml": INIT_PERSONA,
             root / ".env.example": INIT_ENV}
    existing = [str(p) for p in files if p.exists()]
    if existing:
        return _err(f"refusing to overwrite {existing}")
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"created {path}")
    print("next: edit target/tools in murphy.yaml, then `murphy validate` and `murphy run`")
    return EXIT_OK


def cmd_validate(args) -> int:
    from murphy.checks import build_checks
    from murphy.config.loader import load_config

    cfg = load_config(args.config)
    build_checks(cfg.checks)
    print(f"✓ {cfg.source}")
    print(f"  target   {cfg.target.type} {cfg.target.extras}")
    print(f"  tools    {[t.name for t in cfg.tools] or 'none'}")
    print(f"  matrix   {len(cfg.personas)} personas × {len(cfg.faults)} fault scenarios")
    print(f"  policy   {cfg.policy.mode}, {len(cfg.policy.rules)} rules · checks {[c.id for c in cfg.checks]}")
    return EXIT_OK


def cmd_check(args) -> int:
    from murphy.config.loader import load_config

    cfg = load_config(args.config)
    import os

    base = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
    models: set[str] = set()
    ok = True
    needed = [("user.model", cfg.user.extras.get("model")), ("target.model", cfg.target.extras.get("model"))]
    if any(m and m.startswith("ollama") for _, m in needed):
        try:
            with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as resp:
                models = {m["name"] for m in json.load(resp)["models"]}
            print(f"✓ ollama reachable at {base} ({len(models)} models)")
        except Exception as exc:
            ok = False
            print(f"✗ ollama not reachable at {base}: {exc}")
    for field, model in needed:
        if not model:
            continue
        if model.startswith("ollama"):
            name = model.split("/", 1)[1]
            present = name in models or f"{name}:latest" in models
            ok &= present
            print(f"{'✓' if present else '✗'} {field}={model}" + ("" if present else f"  (run: ollama pull {name})"))
        else:
            print(f"• {field}={model} (hosted; needs its API key)")
    target_model = cfg.target.extras.get("model")
    if ok and target_model and not args.skip_tools:
        ok &= asyncio.run(_tool_calling(target_model))
    return EXIT_OK if ok else EXIT_FAIL


async def _tool_calling(model: str) -> bool:
    import litellm

    tool = {"type": "function", "function": {
        "name": "get_order", "description": "Get an order by ID",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}}
    try:
        resp = await litellm.acompletion(model=model, temperature=0, tools=[tool],
                                         messages=[{"role": "user", "content": "Look up order A12 using the tool."}])
        calls = resp.choices[0].message.tool_calls or []
        good = any(c.function.name == "get_order" and "A12" in c.function.arguments for c in calls)
    except Exception as exc:
        print(f"✗ tool calling with {model}: {exc}")
        return False
    print(f"{'✓' if good else '✗'} tool calling with {model}" + ("" if good else ": model did not call the tool"))
    return good


def cmd_run(args) -> int:
    from murphy import report
    from murphy.checks import build_checks
    from murphy.config.loader import load_config
    from murphy.core.ci import evaluate
    from murphy.core.orchestrator import matrix_dir_for, run_matrix
    from murphy.targets import build_target, target_label
    from murphy.users import build_user

    cfg = load_config(args.config)
    if args.seed is not None:
        cfg.seed = args.seed
    personas = _select(cfg.personas, _ids(args.personas), "personas")
    scenarios = _select(cfg.faults, _ids(args.faults), "fault scenarios")
    checks = build_checks(cfg.checks)
    mode = args.policy or cfg.policy.mode
    label = target_label(cfg.target, args.target)
    out = matrix_dir_for(Path(args.out), cfg, label, mode)
    print(f"murphy {__version__} · {cfg.name} · {len(personas)} personas × {len(scenarios)} faults · "
          f"target {label} · policy {mode}")

    def progress(r):
        status = "PASS" if r.passed else "FAIL " + ",".join(r.labels)
        print(f"  {r.persona:<20} {r.fault:<14} {status:<16} {r.turns} turns · {r.tool_calls} tools · {r.wall_s}s")

    asyncio.run(run_matrix(
        cfg, personas, scenarios, lambda: build_target(cfg.target, args.target),
        lambda p: build_user(cfg.user, p, cfg.seed, cfg.max_turns(p)), checks, out, mode, progress,
    ))
    data = report.write_all(out)
    print()
    print(report.terminal(data))
    print(f"report: {out / 'report.html'}   (open with: murphy ui {out})")
    tripped = evaluate(data["totals"], cfg.ci.fail_if)
    for reason in tripped:
        print(f"CI FAIL: {reason}")
    return EXIT_FAIL if tripped else EXIT_OK


def cmd_report(args) -> int:
    from murphy import report

    data = report.write_all(Path(args.matrix_dir))
    print(report.terminal(data))
    return EXIT_OK


def cmd_chat(args) -> int:
    """You play the user; Murphy still injects faults, enforces policies, records and judges."""
    from murphy import report
    from murphy.checks import build_checks
    from murphy.config.loader import load_config
    from murphy.core.orchestrator import matrix_dir_for, run_matrix
    from murphy.report.text import tool_mark
    from murphy.targets import build_target, target_label
    from murphy.users.human import HELP, HumanUser

    cfg = load_config(args.config)
    persona = _select(cfg.personas, _ids(args.persona), "personas")[0] if args.persona else cfg.personas[0]
    persona = persona.model_copy(update={"max_turns": 50})  # a human decides when to stop
    scenario = _select(cfg.faults, _ids(args.fault), "fault scenarios")[0] if args.fault else cfg.faults[0]
    cfg.limits.run_timeout_s = 3600  # typing takes longer than a simulator
    mode = args.policy or cfg.policy.mode
    label = target_label(cfg.target, args.target)
    out = matrix_dir_for(Path(args.out), cfg, f"chat-{label}", mode)

    print(f"Murphy chat · {cfg.name} · target {label} · fault {scenario.id} · policy {mode}")
    print(f"You are playing: {persona.id}. Goal: {persona.goal}")
    if persona.facts:
        print("Facts you may share: " + "; ".join(f"{k}={v}" for k, v in persona.facts.items()))
    print(f"({HELP})\n")

    def show(event: dict) -> None:
        if event["kind"] == "agent":
            print(f"agent › {event['text']}\n")
        elif event["kind"] == "tool":
            args_text = ", ".join(f"{k}={v}" for k, v in (event.get("args") or {}).items())
            print(f"  ⚙ {event['tool']}({args_text})  {tool_mark(event)}")

    [result] = asyncio.run(run_matrix(
        cfg, [persona], [scenario], lambda: build_target(cfg.target, args.target), lambda p: HumanUser(),
        build_checks(cfg.checks), out, mode, on_event=show,
    ))
    report.write_all(out)
    print(f"\n{'PASS' if result.passed else 'FAIL ' + ', '.join(result.labels)} · ended: {result.end_reason}")
    for check in result.checks:
        print(f"  {'✓' if check['passed'] else '✗'} {check['id']}: {check['message']}")
    if result.hint:
        print(f"  hint: {result.hint}")
    cell = out / f"{persona.id}__{scenario.id}"
    print(f"\nreport: murphy ui {out}")
    print(f"replay: murphy replay {cell} --target <fixed agent>   (or --policy enforce)")
    return EXIT_OK if result.passed else EXIT_FAIL


def cmd_replay(args) -> int:
    from murphy import report
    from murphy.checks import build_checks
    from murphy.config.loader import load_config
    from murphy.replay import render_diff, replay
    from murphy.targets import build_target
    from murphy.users import build_user

    cell = Path(args.cell_dir).resolve()
    meta = json.loads((cell / "meta.json").read_text())
    cfg = load_config(args.config or meta.get("config"))
    persona = cfg.persona(meta["persona"])
    fallback = None if args.no_fallback else build_user(cfg.user, persona, meta["seed"], cfg.max_turns(persona))
    ref = args.target or meta["target"]  # default: the agent that was recorded
    try:
        target = build_target(cfg.target, ref)
    except (ImportError, AttributeError) as exc:
        if args.target:
            raise
        return _err(f"recorded target {ref!r} can't be loaded ({exc}); pass --target to choose one")
    before, after, out = asyncio.run(replay(cfg, cell, target, build_checks(cfg.checks), fallback, args.policy))
    print(render_diff(before, after, cell, out))
    report.write_all(cell.parent)
    print(f"report updated: {cell.parent / 'report.html'}")
    return EXIT_OK if after.passed else EXIT_FAIL


def _resolve_matrix(path: str | None) -> Path:
    p = Path(path or "runs/latest")
    if not p.exists() and (p.parent / "LATEST").exists():
        p = p.parent / (p.parent / "LATEST").read_text().strip()
    return p.resolve()


def cmd_ui(args) -> int:
    from murphy import report

    matrix = _resolve_matrix(args.matrix_dir)
    if not matrix.is_dir():
        return _err(f"{matrix} does not exist (paths are relative to {Path.cwd()})")
    if not (matrix / "report.html").exists():
        if not any(matrix.glob("*/result.json")):
            return _err(f"no runs found in {matrix}")
        report.write_all(matrix)
    page = matrix / "report.html"
    if args.serve:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(matrix.parent))
        url = f"http://127.0.0.1:{args.serve}/{matrix.name}/report.html"
        print(f"serving {matrix.parent} at {url} (Ctrl+C to stop)")
        if not args.no_open:
            webbrowser.open(url)
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.serve), handler) as server:
            server.serve_forever()
        return EXIT_OK
    print(page)
    if not args.no_open:
        webbrowser.open(page.as_uri())
    return EXIT_OK


# ---------------------------------------------------------------- parser

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="murphy", description="Stress-test tool-using AI agents.")
    p.add_argument("--version", action="version", version=f"murphy {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def cfg_arg(sp):
        sp.add_argument("-c", "--config", help="path to murphy.yaml (default ./murphy.yaml or $MURPHY_CONFIG)")

    s = sub.add_parser("init", help="scaffold murphy.yaml, an example persona and .env.example")
    s.add_argument("dir", nargs="?", default=".")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("validate", help="load and validate the config")
    cfg_arg(s)
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("check", help="check Ollama, models and target-model tool calling")
    cfg_arg(s)
    s.add_argument("--skip-tools", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("run", help="run the persona × fault matrix")
    cfg_arg(s)
    s.add_argument("--personas", help="comma-separated persona ids (default all)")
    s.add_argument("--faults", help="comma-separated fault scenario ids (default all)")
    s.add_argument("--policy", choices=["off", "monitor", "enforce"], help="override policy.mode")
    s.add_argument("--target", help="override the target (adk factory / scripted policy / http url)")
    s.add_argument("--seed", type=int)
    s.add_argument("--out", default="runs", help="runs directory (default ./runs)")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("report", help="re-render all reports for a matrix directory")
    s.add_argument("matrix_dir")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("chat", help="play the user yourself; Murphy injects faults and judges the run")
    cfg_arg(s)
    s.add_argument("--persona", help="persona whose goal/expected outcome you play (default: first)")
    s.add_argument("--fault", help="fault scenario id (default: first, usually no-fault)")
    s.add_argument("--policy", choices=["off", "monitor", "enforce"], help="override policy.mode")
    s.add_argument("--target", help="override the target (adk factory / scripted policy / http url)")
    s.add_argument("--out", default="runs", help="runs directory (default ./runs)")
    s.set_defaults(func=cmd_chat)

    s = sub.add_parser("replay", help="replay a recorded run (same user turns, faults, seed)")
    s.add_argument("cell_dir")
    cfg_arg(s)
    s.add_argument("--target", help="target to replay against (default: the recorded target), e.g. a fixed agent factory")
    s.add_argument("--policy", choices=["off", "monitor", "enforce"])
    s.add_argument("--no-fallback", action="store_true", help="no live simulator after recorded turns run out")
    s.set_defaults(func=cmd_replay)

    s = sub.add_parser("ui", help="open the HTML report (default runs/latest)")
    s.add_argument("matrix_dir", nargs="?")
    s.add_argument("--serve", type=int, metavar="PORT", help="serve over http instead of opening the file")
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(func=cmd_ui)
    return p


def main(argv: list[str] | None = None) -> int:
    from murphy.config.loader import ConfigError

    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    try:
        return args.func(args)
    except ConfigError as exc:
        return _err(str(exc))
    except (ValueError, KeyError, FileNotFoundError, ImportError, AttributeError) as exc:
        return _err(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())

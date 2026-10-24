"""Fault-injecting, policy-enforcing, recording MCP proxy in front of the user's MCP servers.

Run as `python -m murphy.proxy <run_dir>`; configuration comes from <run_dir>/proxy.json:
  {"upstreams": [{name, command, env, cwd}], "faults": [FaultSpec], "policy": {mode, rules}, "seed": int}
Tool events are appended to <run_dir>/tools.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError
from fastmcp.server import create_proxy
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from pydantic import TypeAdapter

from murphy.config.schema import FaultSpec, PolicyConfig, Upstream
from murphy.proxy.faults import FaultEngine
from murphy.proxy.policy import PolicyEngine

RUN_DIR_ENV = "MURPHY_RUN_DIR"
EVENT_VERSION = 1


def result_dict(result: ToolResult) -> dict | None:
    if isinstance(result.structured_content, dict):
        return result.structured_content
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                data = json.loads(text)
                return data if isinstance(data, dict) else {"value": data}
            except json.JSONDecodeError:
                return {"text": text}
    return None


class StressMiddleware(Middleware):
    def __init__(self, faults: FaultEngine, policy: PolicyEngine, trace_path: Path | None) -> None:
        self.faults = faults
        self.policy = policy
        self.trace_path = trace_path
        self.counts: Counter[str] = Counter()
        self.seq = 0

    def _record(self, event: dict) -> None:
        if self.trace_path is not None:
            with self.trace_path.open("a") as f:
                f.write(json.dumps(event) + "\n")

    async def on_call_tool(self, context, call_next):
        tool = context.message.name
        args: dict[str, Any] = dict(context.message.arguments or {})
        self.seq += 1
        self.counts[tool] += 1
        start = time.time()
        event = {
            "v": EVENT_VERSION, "kind": "tool", "ts": start, "seq": self.seq, "tool": tool, "args": args,
            "fault": None, "upstream_called": False, "ok": False, "result": None, "error": None,
            "policy": {"violations": [], "blocked": False},
        }

        def finish(**fields) -> None:
            # Raw values: checks must judge real arguments. Recorder.merge() redacts what is persisted.
            event.update(fields, latency_ms=round((time.time() - start) * 1000))
            self._record(event)

        violations = self.policy.check(tool, args)
        event["policy"]["violations"] = violations
        if violations and self.policy.enforcing:
            event["policy"]["blocked"] = True
            msg = f"blocked by policy: {', '.join(violations)}"
            finish(error=msg)
            raise ToolError(msg)

        fault = self.faults.pick(tool, self.counts[tool])
        event["fault"] = fault.type if fault else None
        if fault and fault.type == "error_500":
            finish(error="500 internal server error")
            raise ToolError("500 internal server error")
        if fault and fault.type == "slow":
            await asyncio.sleep(fault.delay_s)

        try:
            result = await call_next(context)
        except Exception as exc:  # upstream errors pass through unchanged
            self.policy.observe(tool, args, None, upstream_ok=False)
            finish(upstream_called=True, error=str(exc))
            raise
        data = result_dict(result)
        self.policy.observe(tool, args, data, upstream_ok=True)

        if fault and fault.type == "timeout_after_commit":
            finish(upstream_called=True, result=data, error="upstream timeout after 30s (committed)")
            raise ToolError("upstream timeout after 30s")
        if fault and fault.type == "malformed" and data:
            bad = dict(list(data.items())[1:])
            finish(upstream_called=True, ok=True, result=bad)
            return ToolResult(content=json.dumps(bad), structured_content=bad)
        finish(upstream_called=True, ok=True, result=data)
        return result


def _transport(upstream: Upstream, run_dir: Path) -> StdioTransport:
    base = dict(os.environ) if upstream.inherit_env else {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    env = {**base, RUN_DIR_ENV: str(run_dir), "FASTMCP_LOG_LEVEL": os.environ.get("FASTMCP_LOG_LEVEL", "WARNING"),
           **upstream.env}
    return StdioTransport(command=upstream.command[0], args=upstream.command[1:], env=env, cwd=upstream.cwd)


def build_proxy(run_dir: Path) -> FastMCP:
    spec = json.loads((run_dir / "proxy.json").read_text())
    upstreams = [Upstream.model_validate(u) for u in spec["upstreams"]]
    if not upstreams:
        raise SystemExit("proxy.json: no upstreams configured")
    faults = FaultEngine(TypeAdapter(list[FaultSpec]).validate_python(spec.get("faults", [])), seed=spec.get("seed", 0))
    policy_cfg = PolicyConfig.model_validate(spec.get("policy", {}))
    policy = PolicyEngine(policy_cfg.rules, policy_cfg.mode)

    if len(upstreams) == 1:
        proxy = create_proxy(_transport(upstreams[0], run_dir), name="murphy-proxy")
    else:
        proxy = FastMCP("murphy-proxy")
        for upstream in upstreams:
            proxy.mount(create_proxy(_transport(upstream, run_dir), name=upstream.name), namespace=upstream.name)
    proxy.add_middleware(StressMiddleware(faults, policy, run_dir / "tools.jsonl"))
    return proxy

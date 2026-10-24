"""Plain-text renderings: run timeline, terminal scorecard, Markdown report."""

from __future__ import annotations

import json


def _clip(text, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _args(args: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items())


def _summary(result) -> str:
    """Generic one-line result: compact JSON, clipped. No knowledge of any tool's fields."""
    if result is None:
        return "ok"
    text = result if isinstance(result, str) else json.dumps(result, separators=(",", ":"), default=str)
    return _clip(text, 60)


def tool_mark(e: dict) -> str:
    policy = e.get("policy", {})
    if policy.get("blocked"):
        return f"⛔ BLOCKED by policy ({', '.join(policy.get('violations', []))})"
    if e.get("fault") == "timeout_after_commit":
        return "⚡ TIMEOUT (injected, but committed)"
    if e.get("fault") == "error_500":
        return "⚡ 500 (injected)"
    if not e.get("ok"):
        return f"✗ {_clip(e.get('error') or 'error', 50)}"
    mark = "✓ " + _summary(e.get("result"))
    if e.get("fault") in ("slow", "malformed"):
        mark += f"  ⚡ {e['fault']} (injected)"
    if policy.get("violations"):
        mark += f"  ⚠ policy: {', '.join(policy['violations'])}"
    return mark


def timeline(trace: list[dict]) -> list[str]:
    lines, t = [], 0
    for e in trace:
        if e["kind"] == "user":
            status = "" if e.get("status", "continue") == "continue" else f"  [{e['status']}]"
            if e.get("text"):
                t += 1
                lines.append(f" t{t:<3}USER   {_clip(e['text'])}{status}")
            elif status:
                lines.append(f"      USER   (ends){status}")
        elif e["kind"] == "agent":
            lines.append(f"      AGENT  {_clip(e['text'])}")
        elif e["kind"] == "tool":
            lines.append(f"      TOOL   → {e['tool']}({_args(e['args'])})  {tool_mark(e)}")
    return lines


def _cell(result: dict) -> str:
    return "PASS" if result["passed"] else "FAIL " + (result["labels"][0] if result["labels"] else "")


def scorecard(data: dict) -> list[str]:
    grid = {(r["result"]["persona"], r["result"]["fault"]): r["result"] for r in data["runs"]}
    width = max([12, *(len(f) + 2 for f in data["faults"])])
    pw = max([10, *(len(p) + 2 for p in data["personas"])])
    lines = [" " * pw + "".join(f.ljust(width) for f in data["faults"])]
    for p in data["personas"]:
        lines.append(p.ljust(pw) + "".join((_cell(grid[(p, f)]) if (p, f) in grid else "-").ljust(width)
                                           for f in data["faults"]))
    t = data["totals"]
    labels = ", ".join(f"{k}={v}" for k, v in sorted(t["labels"].items())) or "none"
    lines += [
        "",
        f"completion        {t['passed']}/{t['runs']} ({round(100 * t['completion'])}%)",
        f"failure labels    {labels}",
        f"avg user turns    {t['avg_turns']}",
        f"faults fired      {t['faults_fired']}",
        f"policy            {t['policy_violations']} violations, {t['policy_blocks']} blocked",
        f"agent tokens      {t['agent_tokens']}" + (f" ({t['agent_tokens_per_success']}/success)" if t["agent_tokens_per_success"] else ""),
    ]
    if t["cost_per_success"] is not None:
        lines.append(f"cost/success      ${t['cost_per_success']}")
    return lines


def terminal(data: dict) -> str:
    head = f"{data['project'].get('name', '')} · target {data['target']} · policy {data['policy_mode']} · seed {data['seed']}"
    return "\n".join([head, "", *scorecard(data)]) + "\n"


def markdown(data: dict) -> str:
    out = [f"# murphy report: {data['matrix']}", "",
           f"project `{data['project'].get('name', '')}` · target `{data['target']}` · policy `{data['policy_mode']}` "
           f"· seed {data['seed']} · {data['totals']['runs']} runs", "", "```", *scorecard(data), "```"]
    failures = [r for r in data["runs"] if not r["result"]["passed"]]
    if failures:
        out += ["", "## Failures"]
    for run in failures:
        r = run["result"]
        failed = [c for c in r["checks"] if not c["passed"]]
        out += ["", f"### ✗ {r['persona']} × {r['fault']} — {', '.join(r['labels'])}", "```", *timeline(run["trace"]), "",
                f" end      {r['end_reason']} · {r['turns']} turns · {r['tool_calls']} tool calls"]
        out += [f" check    {c['id']}: {c['message']}" for c in failed]
        if r["hint"]:
            out.append(f" hint     {r['hint']}")
        out += [f" replay   murphy replay runs/{data['matrix']}/{run['cell']} --target <fixed-target>", "```"]
    return "\n".join(out) + "\n"

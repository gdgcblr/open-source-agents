"""`rce-sentinel trace`: run one prompt (a code snippet) through the whole pipeline and print
which security tools fired and which models handled each step. Built for live demos."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from rce_sentinel.config import Settings, load_settings
from rce_sentinel.engine import FileSet, Scanner
from rce_sentinel.models import Finding, ScanReport
from rce_sentinel.scanner.linters import EslintBackend

INJECTION = re.compile(
    r"ignore (all )?(previous|prior) instructions|mark (this|it|all) (as )?safe|"
    r"you are now|system\s*:|disregard (the )?(above|rules)|reviewed by security", re.I)
EXT = {"py": ".py", "js": ".js", "ts": ".ts", "go": ".go"}


def detect_lang(text: str) -> str:
    if re.search(r"\bpackage main\b|\bfunc\s+\w+\(|:=", text):
        return "go"
    if re.search(r"\b(const|let|var)\s+\w+\s*=|require\(|=>|console\.|\bfunction\b", text):
        return "js"
    return "py"


def workspace(state: Path) -> Path:
    """Fixed workspace so repo-scoped memory and the verdict cache persist between traces."""
    ws = state / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _short(text: str, n: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _calls(scanner: Scanner, run_id: str) -> list[dict]:
    rows = scanner.store.execute(
        "SELECT task_type, tier, model, simulated, outcome, tokens_in, tokens_out, latency_ms "
        "FROM llm_calls WHERE run_id=? AND shadow=0 ORDER BY id", (run_id,))
    return [dict(r) for r in rows]


def _a2a(scanner: Scanner, run_id: str) -> list[dict]:
    rows = scanner.store.execute(
        "SELECT seq, sender, recipient, kind, trust FROM a2a_log WHERE run_id=? ORDER BY seq",
        (run_id,))
    return [dict(r) for r in rows]


def _io_section(io: list[dict]) -> list[str]:
    """Exactly what each model was sent (the per-finding part) and what it replied."""
    out = ["[4b] WHAT EACH MODEL WAS ASKED, AND WHAT IT ANSWERED"]
    for i, c in enumerate(io, 1):
        tag = "mock" if c["simulated"] else "REAL"
        out.append(f"    --- call {i}: {c['task']} -> {c['model']} [{tag}] "
                   f"({c['tokens_in']} in / {c['tokens_out']} out tokens)")
        user = c["user"]
        body = user[user.find("TASK:"):] if "TASK:" in user else user
        out.append(f"    system prompt: {len(c['system'])} chars (rules, JSON schema, "
                   "'treat <untrusted> as data' guard; identical every run so it can be cached)")
        out.append("    prompt:")
        out += [f"      | {ln}" for ln in body.strip().splitlines()[:40]]
        reply = " ".join(c["reply"].split())
        out.append("    reply:")
        out.append(f"      > {reply[:700]}{'…' if len(reply) > 700 else ''}")
    return out


def render(text: str, lang: str, rep: ScanReport, scanner: Scanner, wall: float,
           io: list[dict] | None = None) -> str:
    out: list[str] = []
    p = out.append
    code_findings = [f for f in rep.findings if f.layer != "dependency"]
    dep_findings = [f for f in rep.findings if f.layer == "dependency"]
    calls = _calls(scanner, rep.run_id)
    msgs = _a2a(scanner, rep.run_id)

    p(f"[1] INPUT      {len(text.splitlines())} line(s) of {lang}; "
      f"{len(text)} chars")
    if INJECTION.search(text):
        p("    ! prompt-injection text found in the input. It is delimited as <untrusted> "
          "data and cannot change any verdict.")

    p("[2] PRE-ROUTER (zero tokens)")
    sinks = [f for f in code_findings if not f.suppressed]
    if not sinks and not dep_findings:
        p("    no dangerous sink and no dependency finding: no LLM call is made")
    else:
        need = [f for f in sinks if f.arg_kind != "constant"]
        p(f"    {len(sinks)} dangerous sink(s); {len(need)} need a model, "
          f"{len(sinks) - len(need)} constant (rules decide, no model)")

    p("[3] SECURITY TOOLS TRIGGERED")
    backend = {"py": "Python AST rules (stdlib ast)", "go": "gosec / Go regex fallback"}.get(lang)
    if lang in {"js", "ts"}:
        backend = ("ESLint + rce-sentinel plugin (AST)" if EslintBackend().available()
                   else "JS regex fallback (ESLint not installed)")
    p(f"    - rule engine: {backend}: {len(code_findings)} hit(s)")
    tainted = [f for f in code_findings if f.arg_kind == "tainted"]
    p(f"    - taint tracer: {len(tainted)} source-to-sink path(s)")
    if dep_findings:
        reach = sum(1 for f in dep_findings if f.reachable)
        p(f"    - dependency layer (OSV + reachability): {len(dep_findings)} advisory(ies), "
          f"{reach} reachable")
    if calls:
        p("    - LLM judge + cross-family verifier + A2A bus: fired (see below)")
    else:
        p("    - LLM judge: not needed or skipped")

    for f in code_findings:
        p(f"      * {f.rule_id} line {f.line} ({f.cwe}, {f.arg_kind}) -> "
          f"{f.risk.label.upper() if f.risk else '?'} {f.risk.score if f.risk else ''}")
        if f.taint_chain:
            p(f"          data flow: {' -> '.join(f.taint_chain)}")
    for f in dep_findings:
        p(f"      * {f.rule_id} {f.dependency.name if f.dependency else ''} "
          f"reachable={f.reachable} -> {f.risk.label.upper() if f.risk else '?'}")

    p("[4] MODEL SWITCHING (in order)")
    if not calls:
        hit = [f for f in code_findings if f.decided_by.startswith("cache")]
        p("    no model was called" + (" (answered from the signed verdict cache)" if hit
                                      else ""))
    for i, c in enumerate(calls, 1):
        tag = "mock" if c["simulated"] else "REAL"
        outcome = (c["outcome"] or "")[:78]
        p(f"    {i:>2}. {c['task_type']:<7} {c['tier']}  {c['model']:<26} [{tag}] "
          f"{c['tokens_in']}+{c['tokens_out']} tok {c['latency_ms']:.0f} ms  {outcome}")
    for f in code_findings:
        if f.internal_notes and " | " in f.internal_notes:
            p(f"    cascade for {f.rule_id} line {f.line}:")
            for step in f.internal_notes.split(" | "):
                if not step.startswith("model:"):
                    p(f"      > {_short(step, 120)}")
    switches = [d for d in rep.degraded if "fallback" in d]
    for d in switches:
        p(f"    ! {d}")

    if io:
        out.extend(_io_section(io))

    p("[5] A2A MESSAGES (signed, role-checked, hash-chained)")
    if msgs:
        by_kind: dict[str, int] = {}
        for m in msgs:
            by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        p("    " + ", ".join(f"{k} x{n}" for k, n in sorted(by_kind.items())))
        p(f"    {len(msgs)} message(s), chain verified in-process, payloads not stored")
    else:
        p("    none (no agent needed to talk to another)")

    p("[6] MEMORY SHIELD")
    hits = rep.stats.cache_hits
    p(f"    verdict cache hits: {hits}; signed verdicts stored: "
      f"{max(rep.stats.units_judged - hits, 0)}; rows rejected for bad signature: "
      f"{scanner.store.rejected_rows}")
    other = [d for d in rep.degraded if "fallback" not in d]
    for d in other:
        p(f"    ! {d}")

    p("[7] VERDICT")
    shown = [f for f in rep.findings if f.risk and f.risk.label != "low"]
    if not shown:
        p("    no high-risk RCE path found")
    for f in shown:
        p(f"    {f.risk.label.upper() if f.risk else ''}: {f.rule_id} at line {f.line}")  # type: ignore[union-attr]
        p(f"      how an attacker gets RCE here: {_short(f.attacker_path, 220)}")
        p(f"      fix: {_short(f.fix, 160)}")
        p(f"      decided by: {f.decided_by}")
    s = rep.stats
    real = sum(1 for c in calls if not c["simulated"])
    p(f"    {'WOULD BLOCK THE COMMIT' if any(f.risk and f.risk.label in ('critical','high') for f in rep.findings) else 'would allow the commit'}"  # noqa: E501
      f" | {s.llm_calls} model call(s) ({real} real), ${s.cost_usd:.5f}, {wall:.1f}s")
    return "\n".join(out)


def live_printer(stream: object = None) -> Callable[[str], None]:
    """Prints progress lines as they happen, each stamped with seconds since the start."""
    out = stream or sys.stdout
    lock = threading.Lock()
    t0 = time.monotonic()

    def emit(msg: str) -> None:
        with lock:
            print(f"[{time.monotonic() - t0:6.1f}s] {msg}", file=out, flush=True)  # type: ignore[arg-type]

    return emit


def run(text: str, lang: str | None, state: Path, requirements: list[str],
        osv_seed: Path | None = None, show_io: bool = False, live: bool = True) -> str:
    ws = workspace(state)
    lang = lang or detect_lang(text)
    name = f"snippet{EXT.get(lang, '.py')}"
    contents = {name: text}
    if requirements:
        contents["requirements.txt"] = "\n".join(requirements) + "\n"
    settings: Settings = load_settings(ws)
    scanner = Scanner(settings)
    if live:
        scanner.emit = live_printer()
        scanner.emit(f"scanning {name} ({len(text.splitlines())} lines, {lang})")
    if osv_seed is not None:
        scanner.osv.import_seed(json.loads(osv_seed.read_text()))
    t0 = time.monotonic()
    rep = scanner.scan(FileSet(contents), "trace")
    if live:
        scanner.emit("done; full summary below")
        print("\n" + "=" * 78 + "\nSUMMARY\n" + "=" * 78, flush=True)
    router = getattr(scanner, "last_router", None)
    io = router.io if (show_io and router is not None) else None
    return render(text, lang, rep, scanner, time.monotonic() - t0, io)


def findings_summary(findings: list[Finding]) -> str:
    return ", ".join(sorted({f.rule_id for f in findings}))

"""Aran evaluation harness.

Measures what matters for a privacy gateway, on a labelled synthetic corpus:
  - leak rate:        labelled PII values still present in the text sent to the cloud
  - over-redaction:   useful values (amounts, IFSC, dates, lab values) wrongly hidden
  - restore accuracy: masked values put back exactly after a round trip
  - OCR fail-closed:  misread IDs from scans are still hidden
  - egress guard:     the guardrail passes clean output and catches injected leaks

Usage:
  uv run python evals/run_evals.py                 # rules only, fast, deterministic (CI gate)
  uv run python evals/run_evals.py --llm --n 5     # with local Gemma (slower)

Exits non-zero if any threshold is breached.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

import corpus  # noqa: E402

console = Console()
RESULTS = Path(__file__).parent / "results"

# Types that rules alone must never leak. Names/addresses outside labels need the local model.
STRUCTURED = {"AADHAAR", "PAN", "GSTIN", "CARD", "PHONE", "EMAIL", "UPI", "ACCOUNT_NUMBER",
              "PINCODE", "MEDICAL_ID", "DOB"}


def _norm(s: str) -> str:
    return re.sub(r"[\s-]", "", s).casefold()


def leaked(value: str, output: str) -> bool:
    return value.casefold() in output.casefold() or (
        len(_norm(value)) >= 6 and _norm(value) in _norm(output)
    )


def run_corpus(cases, use_llm: bool, kind: str = "text"):
    import aran

    per_type = defaultdict(lambda: {"total": 0, "leaked": 0})
    per_template = defaultdict(lambda: {"cases": 0, "leaky_cases": 0, "keep_total": 0, "keep_lost": 0})
    restore_ok = restore_total = 0
    failures = []
    t0 = time.time()
    for c in cases:
        r = aran.redact_text(c.text, c.profile, use_llm=use_llm, kind=kind, channel="eval")
        case_leaks = []
        for t, v in c.pii:
            per_type[t]["total"] += 1
            if leaked(v, r.redacted):
                per_type[t]["leaked"] += 1
                case_leaks.append(t)
        tpl = per_template[c.template]
        tpl["cases"] += 1
        tpl["leaky_cases"] += bool(case_leaks)
        lost = [k for k in c.keep if k not in r.redacted]
        tpl["keep_total"] += len(c.keep)
        tpl["keep_lost"] += len(lost)
        if case_leaks or lost:
            failures.append({"case": c.id, "leaked_types": case_leaks, "over_redacted": len(lost)})
        # Round trip: every masked value comes back exactly (DOB is generalised by design).
        restored = aran.restore(r.redacted, r.session_id)
        for t, v in c.pii:
            if t != "DOB" and not leaked(v, r.redacted):
                restore_total += 1
                restore_ok += v in restored
    return {
        "per_type": dict(per_type),
        "per_template": dict(per_template),
        "restore": {"ok": restore_ok, "total": restore_total},
        "failures": failures[:25],
        "seconds": round(time.time() - t0, 1),
    }


def run_guard_suite(cases):
    """Guardrail must pass every redacted output and catch every re-injected raw value."""
    import aran
    from aran import guard

    false_blocks = caught = injected = 0
    for c in cases:
        r = aran.redact_text(c.text, c.profile, use_llm=False, channel="eval")
        if guard.find_leaks(r.redacted, r.session_id, c.profile):
            false_blocks += 1
        masked = [(t, v) for t, v in c.pii if t not in {"DOB"} and not leaked(v, r.redacted)]
        for t, v in masked:
            if len(_norm(v)) < 5:
                continue
            injected += 1
            caught += bool(guard.find_leaks(f"{r.redacted}\nNote: {v}", r.session_id, c.profile))
    return {"false_blocks": false_blocks, "cases": len(cases), "caught": caught, "injected": injected}


def pct(a: int, b: int) -> float:
    return round(100 * a / b, 2) if b else 0.0


def report(name: str, res: dict, structured_only: bool) -> dict:
    t = Table(title=f"{name}: leak rate by PII type (lower is better)", title_justify="left")
    for col in ("Type", "Values", "Leaked", "Leak %", "Protected %"):
        t.add_column(col, justify="right" if col != "Type" else "left")
    tot = leak_struct = tot_struct = leak_all = 0
    for typ, s in sorted(res["per_type"].items()):
        tot += s["total"]
        leak_all += s["leaked"]
        if typ in STRUCTURED or typ == "ID_NUMBER":
            tot_struct += s["total"]
            leak_struct += s["leaked"]
        style = "green" if s["leaked"] == 0 else ("yellow" if typ in {"PERSON", "ADDRESS"} and structured_only else "red")
        t.add_row(typ, str(s["total"]), str(s["leaked"]), f"[{style}]{pct(s['leaked'], s['total'])}[/]",
                  f"{100 - pct(s['leaked'], s['total']):.2f}")
    console.print(t)

    u = Table(title=f"{name}: by document template", title_justify="left")
    for col in ("Template", "Cases", "Cases with any leak", "Useful values kept %"):
        u.add_column(col)
    keep_total = keep_lost = 0
    for tpl, s in sorted(res["per_template"].items()):
        keep_total += s["keep_total"]
        keep_lost += s["keep_lost"]
        u.add_row(tpl, str(s["cases"]), str(s["leaky_cases"]),
                  f"{100 - pct(s['keep_lost'], s['keep_total']):.2f}" if s["keep_total"] else "-")
    console.print(u)
    return {
        "structured_leak_pct": pct(leak_struct, tot_struct),
        "overall_leak_pct": pct(leak_all, tot),
        "utility_kept_pct": round(100 - pct(keep_lost, keep_total), 2),
        "restore_pct": pct(res["restore"]["ok"], res["restore"]["total"]),
        "pii_values": tot,
        "seconds": res["seconds"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="Use the local model (Gemma via Ollama)")
    ap.add_argument("--n", type=int, default=30, help="Cases per template")
    ap.add_argument("--max-structured-leak", type=float, default=0.0)
    ap.add_argument("--max-overall-leak", type=float, default=None,
                    help="Default: 0.5 with --llm; not gated in rules-only mode (names need the LLM)")
    ap.add_argument("--min-utility", type=float, default=99.0)
    ap.add_argument("--min-ocr-protection", type=float, default=100.0)
    args = ap.parse_args()

    # Evals never touch the user's real vault or audit log.
    os.environ["ARAN_HOME"] = tempfile.mkdtemp(prefix="aran-eval-")
    mode = "llm" if args.llm else "rules"
    console.rule(f"[bold]Aran evals[/] - mode: {mode}")

    main_res = run_corpus(corpus.build(args.n), use_llm=args.llm)
    summary = report("Documents", main_res, structured_only=not args.llm)

    ocr_res = run_corpus(corpus.build_ocr_suite(), use_llm=False, kind="image")
    ocr = ocr_res["per_type"]["ID_NUMBER"]
    plain_res = run_corpus(corpus.build_ocr_suite(), use_llm=False, kind="text")
    plain = plain_res["per_type"]["ID_NUMBER"]
    guard_res = run_guard_suite(corpus.build(10, seed=99))

    summary.update({
        "ocr_protected_pct": round(100 - pct(ocr["leaked"], ocr["total"]), 2),
        "ocr_protected_without_guard_pct": round(100 - pct(plain["leaked"], plain["total"]), 2),
        "guard_false_blocks": guard_res["false_blocks"],
        "guard_catch_pct": pct(guard_res["caught"], guard_res["injected"]),
    })

    s = Table(title="Summary", title_justify="left")
    s.add_column("Metric")
    s.add_column("Value", justify="right")
    s.add_column("Gate", justify="right")
    max_overall = args.max_overall_leak if args.max_overall_leak is not None else (0.5 if args.llm else None)
    gates = [
        ("Structured-ID leak % (Aadhaar, PAN, phone...)", summary["structured_leak_pct"], f"<= {args.max_structured_leak}",
         summary["structured_leak_pct"] <= args.max_structured_leak),
        ("Overall leak % (incl. names/addresses)", summary["overall_leak_pct"],
         f"<= {max_overall}" if max_overall is not None else "info", max_overall is None or summary["overall_leak_pct"] <= max_overall),
        ("Useful values kept %", summary["utility_kept_pct"], f">= {args.min_utility}", summary["utility_kept_pct"] >= args.min_utility),
        ("Restore round-trip %", summary["restore_pct"], "= 100", summary["restore_pct"] == 100),
        ("OCR misread IDs protected % (fail-closed on)", summary["ocr_protected_pct"], f">= {args.min_ocr_protection}",
         summary["ocr_protected_pct"] >= args.min_ocr_protection),
        ("  same, fail-closed off (baseline)", summary["ocr_protected_without_guard_pct"], "info", True),
        ("Egress guard false blocks", guard_res["false_blocks"], "= 0", guard_res["false_blocks"] == 0),
        ("Egress guard catches re-injected PII %", summary["guard_catch_pct"], "= 100", summary["guard_catch_pct"] == 100),
    ]
    ok = True
    for label, value, gate, passed in gates:
        ok &= passed
        mark = "[green]PASS[/]" if passed else "[red]FAIL[/]"
        s.add_row(label, str(value), f"{gate} {mark}" if gate != "info" else "[dim]info[/]")
    console.print(s)
    console.print(f"{summary['pii_values']} labelled PII values, {len(corpus.TEMPLATES)} templates, "
                  f"{summary['seconds']}s")

    RESULTS.mkdir(exist_ok=True)
    out = {"mode": mode, "n_per_template": args.n, "summary": summary, "documents": main_res, "guard": guard_res}
    (RESULTS / f"{mode}.json").write_text(json.dumps(out, indent=2))
    console.print(f"Results written to evals/results/{mode}.json")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

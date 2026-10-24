"""Benchmark: precision / recall / false positives / latency for --no-llm and each Gemma model.

    python benchmark/run_benchmark.py --models gemma4:e2b-it-q4_K_M,gemma4:12b-it-q4_K_M
    python benchmark/run_benchmark.py            # --no-llm only

The fixture is generated into a temp dir at runtime and deleted afterwards. Results are written to
benchmark/results/<timestamp>.json and .md (they contain only redacted data and metadata).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fixtures import build  # noqa: E402

from secret_scanner.llm import OllamaClient, OllamaError  # noqa: E402
from secret_scanner.scanner import scan  # noqa: E402


def score(truth: list[dict], result) -> dict:
    planted = {(t["file"], t["line"]): t for t in truth if t["is_secret"]}
    decoys = {(t["file"], t["line"]): t for t in truth if not t["is_secret"]}
    flagged = {(f.candidate.file, f.candidate.line) for f in result.reportable}
    cand_all = {(f.candidate.file, f.candidate.line) for f in result.findings}
    tp = flagged & set(planted)
    fp = flagged - set(planted)
    missed = set(planted) - flagged
    prec = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 1.0
    rec = len(tp) / len(planted) if planted else 1.0
    # PRIMARY SAFETY METRIC: planted real secrets that were detected but then dismissed by triage.
    dismissed_real = sorted(planted[k]["label"] for k in set(planted) & cand_all if k not in flagged)
    st = result.stats
    n_cand = len(result.findings)
    llm_secs = result.stats.get("triage_seconds", 0.0)
    return {
        "planted": len(planted), "decoys": len(decoys), "candidates": n_cand,
        "true_positives": len(tp), "false_positives": len(fp), "false_negatives": len(missed),
        "dismissed_real_secrets": len(dismissed_real), "dismissed_real_labels": dismissed_real,
        "false_positive_rate": round(len(fp & set(decoys)) / len(decoys), 3) if decoys else 0.0,
        "json_valid_rate": (round(1 - st["llm_invalid_json"] / st["llm_requests"], 3) if st.get("llm_requests") else None),
        "llm_requests": st.get("llm_requests", 0), "llm_timeouts": st.get("llm_timeouts", 0),
        "injection_planted": sum(1 for k, t in planted.items() if t.get("group") == "injection"),
        "injection_dismissed": sum(1 for k in set(planted) & cand_all if k not in flagged and planted[k].get("group") == "injection"),
        "precision": round(prec, 3), "recall": round(rec, 3),
        "decoys_reported": sorted(decoys[k]["label"] for k in fp if k in decoys),
        "unexpected_reports": sum(1 for k in fp if k not in decoys),
        "missed": sorted(planted[k]["label"] for k in missed),
        "missed_unexpectedly": sorted(planted[k]["label"] for k in missed if not planted[k]["expected_miss"]),
        "avg_seconds_per_candidate": round(llm_secs / n_cand, 3) if n_cand else 0.0,
        "total_seconds": result.stats["total_seconds"],
        "decoys_not_even_candidates": len(decoys) - len({k for k in cand_all if k in decoys}),
    }


def run(models: list[str], host: str | None, keep: bool = False, groups=("main", "injection")) -> dict:
    out = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "platform": platform.platform(),
           "host": host or "default", "runs": []}
    with tempfile.TemporaryDirectory(prefix="secretscan-bench-") as td:
        root = Path(td)
        truth = build(root, groups=groups)
        out["fixture"] = {"planted": sum(t["is_secret"] for t in truth), "decoys": sum(not t["is_secret"] for t in truth),
                          "expected_misses": sum(t["expected_miss"] for t in truth)}
        configs: list[tuple[str, str | None]] = [("no-llm", None)] + [(m, m) for m in models]
        for name, model in configs:
            print(f"== {name}", file=sys.stderr)
            try:
                if model is None:
                    res = scan(root, use_llm=False)
                else:
                    cl = OllamaClient(model=model, host=host)
                    try:
                        cl.check()
                        res = scan(root, client=cl)
                    finally:
                        cl.close()
            except OllamaError as e:
                out["runs"].append({"config": name, "skipped": str(e)})
                print(f"   skipped: {e}", file=sys.stderr)
                continue
            m = score(truth, res)
            m["config"] = name
            m["findings"] = [{"file": f.candidate.file, "line": f.candidate.line, "rule": f.candidate.rule,
                              "verdict": f.verdict, "confidence": round(f.confidence, 2),
                              "decided_by": f.decided_by,
                              "label": next((t["label"] for t in truth if (t["file"], t["line"]) == (f.candidate.file, f.candidate.line)), None)}
                             for f in res.findings]
            out["runs"].append(m)
    return out


def to_markdown(r: dict) -> str:
    rows = ["| Config | Dismissed real secrets (must be 0) | Precision | Recall | False positives (FP rate) | Missed | JSON valid | Avg s/candidate | Total s |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in r["runs"]:
        if "skipped" in m:
            rows.append(f"| {m['config']} | skipped | - | - | - | - | - | - | - |")
            continue
        jv = "n/a" if m["json_valid_rate"] is None else f"{m['json_valid_rate']:.2f}"
        rows.append(f"| {m['config']} | {m['dismissed_real_secrets']} | {m['precision']:.2f} | {m['recall']:.2f} | "
                    f"{m['false_positives']} ({m['false_positive_rate']:.2f}) | {m['false_negatives']} | {jv} | "
                    f"{m['avg_seconds_per_candidate']} | {m['total_seconds']} |")
    notes = [f"- `{m['config']}`: skipped - {m['skipped']}" for m in r["runs"] if "skipped" in m]
    return "\n".join([
        f"# Benchmark results ({r['generated']})", "",
        f"Fixture: {r['fixture']['planted']} planted secrets, {r['fixture']['decoys']} decoys "
        f"(generated at runtime; {r['fixture']['expected_misses']} planted secret(s) are deliberate expected misses).",
        f"Platform: {r['platform']}; Ollama host: {r['host']}", "", *rows, "", *notes, "",
        "Precision = TP / (TP + FP) over reported findings; recall = TP / planted. `--no-llm` reports every "
        "deterministic match, so its precision shows the baseline noise that LLM triage must remove.", ""])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="", help="comma-separated Ollama models, e.g. gemma4:e2b-it-q4_K_M,gemma4:12b-it-q4_K_M")
    ap.add_argument("--host", default=None)
    ap.add_argument("--injection-only", action="store_true",
                    help="only the prompt-injection set (real secrets next to 'ignore previous instructions' text)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    r = run(models, a.host, groups=("injection",) if a.injection_only else ("main", "injection"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out / f"benchmark-{stamp}.json").write_text(json.dumps(r, indent=2))
    md = to_markdown(r)
    (out / f"benchmark-{stamp}.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())

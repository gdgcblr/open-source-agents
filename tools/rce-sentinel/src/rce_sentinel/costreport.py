"""Cost dashboard: spend per tier, cache hit rates, caveman savings, and the comparison
against a naive baseline that sends every scanned file to the strongest model."""

from __future__ import annotations

from typing import Any

from rce_sentinel.memory.store import Store
from rce_sentinel.orchestrator.llm import ModelRegistry


def gather(store: Store, registry: ModelRegistry, last: int | None = None) -> dict[str, Any]:
    runs = store.execute("SELECT * FROM runs ORDER BY started DESC" +
                         (f" LIMIT {int(last)}" if last else ""))
    run_ids = [r["run_id"] for r in runs]
    marks = ",".join("?" for _ in run_ids) or "''"
    calls = store.execute(f"SELECT * FROM llm_calls WHERE run_id IN ({marks})",
                          tuple(run_ids))
    real = [c for c in calls if c["shadow"] != 2]
    probes = [c for c in calls if c["shadow"] == 2]
    tiers: dict[str, dict[str, float]] = {}
    for c in real:
        t = tiers.setdefault(c["tier"], {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                                          "cached": 0, "cost": 0.0})
        t["calls"] += 1
        t["tokens_in"] += c["tokens_in"]
        t["tokens_out"] += c["tokens_out"]
        t["cached"] += c["cached_tokens"]
        t["cost"] += c["cost"]
    hits = sum(r["cache_hits"] or 0 for r in runs)
    judged = sum(r["judged"] or 0 for r in runs)
    files = sum(r["units"] or 0 for r in runs)
    prerouted = sum(r["prerouted"] or 0 for r in runs)
    baseline_cost = sum(r["baseline_cost"] or 0.0 for r in runs)
    actual = sum(c["cost"] for c in real)

    by_id = {c["id"]: c for c in calls}
    pairs = []
    for p in probes:
        orig = by_id.get(int(str(p["outcome"]).split(":")[-1] or 0))
        if orig:
            pairs.append((orig["tokens_out"], p["tokens_out"], orig))
    on_sum = sum(a for a, _, _ in pairs)
    off_sum = sum(b for _, b, _ in pairs)
    ratio = off_sum / on_sum if on_sum else None
    caveman_on = [c for c in real if c["caveman"]]
    projected_tokens = int(sum(c["tokens_out"] for c in caveman_on) * (ratio - 1)) \
        if ratio else None
    prices = {m.id: m.price_out for tier in registry.all.values() for m in tier}
    projected_usd = (sum(c["tokens_out"] * (ratio - 1) * prices.get(c["model"], 0.0)
                         for c in caveman_on) / 1_000_000) if ratio else None
    return {
        "runs": len(runs), "files_scanned": files, "prerouted_files": prerouted,
        "units_judged": judged, "result_cache_hits": hits,
        "result_cache_hit_rate": hits / judged if judged else None,
        "tiers": tiers, "llm_calls": len(real), "actual_usd": actual,
        "provider_cached_tokens": sum(t["cached"] for t in tiers.values()),
        "tokens_in": sum(t["tokens_in"] for t in tiers.values()),
        "caveman_pairs": len(pairs), "caveman_out_on": on_sum, "caveman_out_off": off_sum,
        "caveman_ratio": ratio, "caveman_projected_tokens": projected_tokens,
        "caveman_projected_usd": projected_usd,
        "probe_overhead_usd": sum(p["cost"] for p in probes),
        "simulated_calls": sum(1 for c in real if c["simulated"]),
        "baseline_model": registry.baseline().id, "baseline_usd": baseline_cost,
    }


def render(d: dict[str, Any]) -> str:
    lines = [
        "rce-sentinel cost report",
        f"  runs: {d['runs']}   files scanned: {d['files_scanned']}   "
        f"skipped by zero-token pre-router: {d['prerouted_files']}",
        "",
        "  tier    calls   tokens in  tokens out   prompt-cached         USD",
    ]
    for tier in ("tier1", "tier2", "tier3"):
        t = d["tiers"].get(tier, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cached": 0,
                                  "cost": 0.0})
        lines.append(f"  {tier}  {t['calls']:>6} {t['tokens_in']:>11} {t['tokens_out']:>11} "
                     f"{t['cached']:>15} {t['cost']:>11.6f}")
    lines.append(f"  total   {d['llm_calls']:>5} {d['tokens_in']:>11} "
                 f"{sum(t['tokens_out'] for t in d['tiers'].values()):>11} "
                 f"{d['provider_cached_tokens']:>15} {d['actual_usd']:>11.6f}")
    if d["simulated_calls"]:
        lines.append(f"  note: {d['simulated_calls']} of {d['llm_calls']} calls used the mock "
                     "provider (model unavailable); their tokens are chars/4 estimates")
    lines.append("")
    judged = d["units_judged"]
    rate = f"{d['result_cache_hits'] / judged:.0%}" if judged else "n/a"
    lines.append(f"  result cache: {d['result_cache_hits']} of {judged} judged findings "
                 f"served from cache ({rate}), zero LLM calls for those")
    cache_share = (d["provider_cached_tokens"] / d["tokens_in"]) if d["tokens_in"] else 0
    lines.append(f"  provider prompt cache: {cache_share:.0%} of input tokens billed at the "
                 "cached rate")
    if d["caveman_ratio"]:
        saved = d["caveman_out_off"] - d["caveman_out_on"]
        pct = saved / d["caveman_out_off"] if d["caveman_out_off"] else 0
        lines.append(f"  caveman: measured on {d['caveman_pairs']} paired calls, output "
                     f"{d['caveman_out_off']} -> {d['caveman_out_on']} tokens "
                     f"({pct:.0%} fewer)")
        lines.append(f"           projected over all caveman-on calls: "
                     f"{d['caveman_projected_tokens']} output tokens, "
                     f"${d['caveman_projected_usd']:.6f} saved "
                     f"(probe overhead ${d['probe_overhead_usd']:.6f})")
    else:
        lines.append("  caveman: no paired measurement yet "
                     "(run a scan with RCE_SENTINEL_CAVEMAN_PROBE=1)")
    base = d["baseline_usd"]
    lines.append("")
    label = f"naive baseline (every file -> {d['baseline_model']}, no caches):"
    width = len(label) + 1
    lines.append(f"  {label:<{width}}${base:.6f}")
    lines.append(f"  {'rce-sentinel actual:':<{width}}${d['actual_usd']:.6f}")
    if base > 0:
        lines.append(f"  {'savings:':<{width}}{1 - d['actual_usd'] / base:.1%}")
    return "\n".join(lines)

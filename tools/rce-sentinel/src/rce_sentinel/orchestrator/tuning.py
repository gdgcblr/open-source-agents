"""Self-tuning escalation thresholds from the SQLite call log.

For each task type, tier-1 answers are compared with the final accepted verdict (from a
higher tier or a shadow run). The learned threshold is the lowest confidence at which
tier-1 was wrong at most `target` of the time, given enough samples.
"""

from __future__ import annotations

from rce_sentinel.memory.store import Store

GRID = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]


def learned_threshold(store: Store, task_type: str, default: float, min_samples: int,
                      target: float) -> tuple[float, int]:
    rows = store.execute(
        "SELECT confidence, final_agree FROM llm_calls WHERE task_type=? AND tier='tier1' "
        "AND final_agree IS NOT NULL AND confidence IS NOT NULL", (task_type,))
    samples = [(r["confidence"], r["final_agree"]) for r in rows]
    if len(samples) < min_samples:
        return default, len(samples)
    for t in GRID:
        above = [agree for conf, agree in samples if conf >= t]
        if len(above) >= min_samples // 2 and above.count(0) / len(above) <= target:
            return t, len(samples)
    return max(default, GRID[-1]), len(samples)

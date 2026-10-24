"""Phase 3 process X-ray: trace each case's path, compute idle time between steps.

Pure pandas. Finds an event-log sheet (case id + activity + timestamp) and ranks the
transitions where work sits idle the longest.
"""
from __future__ import annotations

import pandas as pd

ID_HINTS = ("order_id", "case_id", "ticket id", "ticket_id", "invoice", "id")
ACT_HINTS = ("activity", "step", "status", "stage", "event")
TS_HINTS = ("timestamp", "time", "date", "datetime")


def detect_event_log(df: pd.DataFrame) -> dict | None:
    """Return {id, activity, timestamp} column names if df looks like an event log."""
    cols = {str(c): str(c).lower() for c in df.columns}

    def pick(hints):
        for h in hints:
            for orig, low in cols.items():
                if h in low:
                    return orig
        return None

    cid, act, ts = pick(ID_HINTS), pick(ACT_HINTS), pick(TS_HINTS)
    if not (cid and act and ts) or len({cid, act, ts}) < 3:
        return None
    parsed = pd.to_datetime(df[ts], errors="coerce", dayfirst=True, format="mixed")
    if parsed.notna().mean() < 0.8 or df[cid].nunique() < 2:
        return None
    # must repeat ids (several events per case), otherwise it is not a log
    if len(df) / df[cid].nunique() < 2:
        return None
    return {"id": cid, "activity": act, "timestamp": ts}


def mine_process(df: pd.DataFrame, cols: dict, idle_threshold_hours: float = 24.0) -> dict:
    d = df[[cols["id"], cols["activity"], cols["timestamp"]]].copy()
    d.columns = ["case", "activity", "ts"]
    d["ts"] = pd.to_datetime(d["ts"], errors="coerce", dayfirst=True, format="mixed")
    d = d.dropna().sort_values(["case", "ts"]).reset_index(drop=True)

    d["next_activity"] = d.groupby("case")["activity"].shift(-1)
    d["next_ts"] = d.groupby("case")["ts"].shift(-1)
    t = d.dropna(subset=["next_ts"]).copy()
    t["gap_hours"] = (t["next_ts"] - t["ts"]).dt.total_seconds() / 3600
    t["transition"] = t["activity"] + " -> " + t["next_activity"]
    t["starts_on_weekend"] = t["ts"].dt.dayofweek >= 5

    n_cases = int(d["case"].nunique())
    ranked = []
    for name, g in t.groupby("transition"):
        slow = g[g["gap_hours"] > idle_threshold_hours]
        ranked.append({
            "transition": name,
            "cases": int(g["case"].nunique()),
            "avg_hours": round(float(g["gap_hours"].mean()), 1),
            "median_hours": round(float(g["gap_hours"].median()), 1),
            "p90_hours": round(float(g["gap_hours"].quantile(0.9)), 1),
            "max_hours": round(float(g["gap_hours"].max()), 1),
            "total_idle_hours": round(float(g["gap_hours"].sum()), 1),
            "cases_over_threshold": int(slow["case"].nunique()),
            "pct_cases_over_threshold": round(slow["case"].nunique() / max(n_cases, 1) * 100, 1),
            "weekend_start_pct": round(float(g["starts_on_weekend"].mean() * 100), 1),
        })
    ranked.sort(key=lambda r: r["avg_hours"], reverse=True)

    paths = d.groupby("case")["activity"].apply(lambda s: " > ".join(s))
    variants = paths.value_counts()
    return {
        "event_log_columns": cols,
        "cases": n_cases,
        "events": int(len(d)),
        "idle_threshold_hours": idle_threshold_hours,
        "top_bottlenecks": ranked[:3],
        "all_transitions": ranked,
        "process_variants": [
            {"path": p, "cases": int(c), "pct": round(c / n_cases * 100, 1)}
            for p, c in variants.head(5).items()
        ],
    }

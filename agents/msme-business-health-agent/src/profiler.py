"""Phase 1 overview: pure pandas, no LLM. Every number here is computed, never estimated."""
from __future__ import annotations

import pandas as pd

from .classifier import classify


def _date_columns(df: pd.DataFrame) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for c in df.columns:
        s = df[c].dropna()
        if s.empty or pd.api.types.is_numeric_dtype(df[c]):
            continue
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True, format="mixed")
        ok = parsed.notna().mean()
        if ok >= 0.6:
            found[c] = {
                "min": str(parsed.min().date()),
                "max": str(parsed.max().date()),
                "invalid_count": int(parsed.isna().sum()),
                "invalid_pct": round(float(parsed.isna().mean() * 100), 1),
            }
    return found


def _rating(score: float) -> str:
    return "Good" if score >= 85 else "Watch" if score >= 65 else "Critical"


def profile_sheet(name: str, df: pd.DataFrame) -> dict:
    rows, cols = df.shape
    if rows == 0 or cols == 0:
        return {"name": name, "department": "Unknown", "rows": 0, "columns": cols,
                "health_score": 0, "health": "Critical", "note": "Sheet is empty after cleaning"}
    cells = rows * cols
    missing_pct = round(float(df.isna().sum().sum() / cells * 100), 1)
    dup_count = int(df.duplicated().sum())
    dup_pct = round(dup_count / rows * 100, 1)
    dates = _date_columns(df)
    invalid_pct = round(sum(d["invalid_pct"] for d in dates.values()) / len(dates), 1) if dates else 0.0
    score = round(max(0.0, 100 - missing_pct - 1.5 * dup_pct - invalid_pct), 1)
    dept = classify(name, df)
    return {
        "name": name,
        "department": dept["department"],
        "department_confidence": dept["confidence"],
        "ask_owner_to_confirm": dept["ask_owner"],
        "rows": rows,
        "columns": cols,
        "column_names": list(df.columns),
        "date_columns": dates,
        "data_quality": {
            "missing_pct": missing_pct,
            "duplicate_rows": dup_count,
            "duplicate_pct": dup_pct,
            "invalid_date_pct": invalid_pct,
        },
        "health_score": score,
        "health": _rating(score),
    }


def build_overview(sheets: dict[str, pd.DataFrame]) -> dict:
    profiles = [profile_sheet(n, d) for n, d in sheets.items()]
    scored = [p for p in profiles if p["rows"] > 0]
    overall = round(sum(p["health_score"] for p in scored) / len(scored), 1) if scored else 0.0
    worst = sorted(scored, key=lambda p: p["health_score"])[:3]
    return {
        "workbook_summary": {
            "sheets": len(profiles),
            "total_rows": sum(p["rows"] for p in profiles),
            "overall_health_score": overall,
            "overall_health": _rating(overall),
        },
        "sheets": profiles,
        "look_first": [f"{p['name']} ({p['health']}, score {p['health_score']})" for p in worst],
    }

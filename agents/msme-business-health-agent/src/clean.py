"""Turn messy raw sheets into tidy DataFrames.

Handles: title rows above the header, blank rows/columns, totals rows at the bottom.
"""
from __future__ import annotations

import pandas as pd

TOTAL_WORDS = ("total", "grand total", "subtotal", "sum")


def _detect_header_row(raw: pd.DataFrame, scan_rows: int = 10) -> int:
    """Header = first row (within scan_rows) where >=60% of the filled cells are text
    and at least 2 cells are filled, and the next row has data."""
    width = max(raw.shape[1], 1)
    for i in range(min(scan_rows, len(raw) - 1)):
        row = raw.iloc[i]
        filled = row.dropna()
        if len(filled) < 2 or len(filled) < 0.5 * width:
            continue
        text_share = sum(isinstance(v, str) for v in filled) / len(filled)
        if text_share >= 0.6:
            return i
    return 0


def clean_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if raw.empty:
        return pd.DataFrame()
    h = _detect_header_row(raw)
    df = raw.iloc[h + 1 :].copy()
    df.columns = [str(c).strip() if pd.notna(c) else f"col_{j}" for j, c in enumerate(raw.iloc[h])]
    df = df.dropna(how="all").reset_index(drop=True)

    # drop totals rows: any text cell that starts with a total word
    def is_total(row) -> bool:
        for v in row:
            if isinstance(v, str) and v.strip().lower().startswith(TOTAL_WORDS):
                return True
        return False

    if len(df):
        df = df[~df.apply(is_total, axis=1)].reset_index(drop=True)

    # convert numeric-looking columns
    for c in df.columns:
        converted = pd.to_numeric(df[c], errors="coerce")
        if converted.notna().sum() >= 0.8 * df[c].notna().sum() and df[c].notna().any():
            df[c] = converted
    return df

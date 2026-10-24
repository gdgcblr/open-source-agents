"""Load a workbook (local .xlsx or Google Sheet) into raw DataFrames, one per tab."""
from __future__ import annotations

import pandas as pd


def load_xlsx(path: str) -> dict[str, pd.DataFrame]:
    """Read every sheet with no header assumption (header row is detected later)."""
    return pd.read_excel(path, sheet_name=None, header=None, dtype=object)


def load_google_sheet(sheet_id: str, credentials_path: str) -> dict[str, pd.DataFrame]:
    """Read every tab of a Google Sheet using a read-only service account."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    book = gspread.authorize(creds).open_by_key(sheet_id)
    out: dict[str, pd.DataFrame] = {}
    for ws in book.worksheets():
        values = ws.get_all_values()
        df = pd.DataFrame(values).replace("", pd.NA) if values else pd.DataFrame()
        out[ws.title] = df
    return out

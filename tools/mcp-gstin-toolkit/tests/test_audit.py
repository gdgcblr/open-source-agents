import csv
from pathlib import Path

import pytest

from gstin_toolkit.audit import audit_csv

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_feed.csv"


def test_sample_feed_summary():
    report = audit_csv(str(SAMPLE))
    assert report["rows"] == 15
    assert report["columns_used"] == {
        "gstin": "supplier_gstin",
        "state": "supplier_state",
        "country": "country",
    }
    assert report["summary"] == {
        "rows_with_issues": 7,
        "rows_with_warnings_only": 5,
        "invalid_gstin": 1,
        "missing_gstin": 1,
        "state_mismatch": 5,
        "unknown_state_value": 0,
        "nonstandard_spelling": 5,
    }
    mismatches = [i for i in report["issues"] if i["issue"] == "state_mismatch"]
    assert {i["line"] for i in mismatches} == {4, 13, 14, 15, 16}
    assert tuple(report["most_common_states"][0]) == ("Uttar Pradesh", 5)


def test_inconsistent_spellings():
    spellings = audit_csv(str(SAMPLE))["inconsistent_spellings"]
    countries = {g["canonical"]: g["variants"] for g in spellings["country"]}
    assert set(countries["AE"]) == {"UAE", "United Arab Emirates"}
    assert set(countries["IN"]) == {"India", "INDIA"}
    states = {g["canonical"]: g["variants"] for g in spellings["state"]}
    assert set(states["29"]) == {"Karnataka", "KA"}
    assert set(states["07"]) == {"Delhi", "New Delhi"}


def test_nonstandard_spellings_flagged_per_row():
    issues = audit_csv(str(SAMPLE))["issues"]
    spelling = {i["line"]: i["detail"] for i in issues if i["issue"] == "nonstandard_spelling"}
    assert spelling == {
        3: "state 'KA' -> 'Karnataka'",
        7: "country 'INDIA' -> 'India'",
        8: "state 'Orissa' -> 'Odisha'",
        10: "country 'UAE' -> 'United Arab Emirates'",
        11: "state 'New Delhi' -> 'Delhi'",
    }


def test_output_csv_has_audit_columns(tmp_path):
    out = tmp_path / "audited.csv"
    audit_csv(str(SAMPLE), output_path=str(out))
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 15
    statuses = [r["audit_status"] for r in rows]
    assert (statuses.count("issue"), statuses.count("warning"), statuses.count("ok")) == (7, 5, 3)
    assert "state_mismatch" in rows[2]["audit_issues"]
    assert "'KA' -> 'Karnataka'" in rows[1]["audit_issues"]


def test_unknown_state_and_missing_column(tmp_path):
    f = tmp_path / "feed.csv"
    f.write_text("gstin,state\n27AAPFU0939F1ZV,Atlantis\n")
    report = audit_csv(str(f))
    assert report["summary"]["unknown_state_value"] == 1
    with pytest.raises(ValueError):
        audit_csv(str(f), gstin_column="nope")

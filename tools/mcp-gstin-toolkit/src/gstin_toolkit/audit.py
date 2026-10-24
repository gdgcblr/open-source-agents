"""Audit a CSV feed for GSTIN problems and inconsistent state/country values."""

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .countries import canonical_country
from .gstin import validate_gstin
from .states import STATE_CODES, codes_match, state_code_for


def _find_column(headers: list[str], hint: str) -> str | None:
    for h in headers:
        if hint in h.lower():
            return h
    return None


def _spelling_groups(values: Counter, canonical) -> list[dict]:
    """Group raw values by canonical form and keep groups spelled more than one way."""
    groups = defaultdict(Counter)
    for raw, count in values.items():
        if raw.strip():
            groups[canonical(raw)][raw] += count
    return [
        {"canonical": key, "variants": dict(variants)}
        for key, variants in groups.items()
        if len(variants) > 1
    ]


def _preferred_spellings(groups: list[dict]) -> dict[str, str]:
    """Map each non-preferred variant to the group's most common (then longest) spelling."""
    preferred = {}
    for group in groups:
        variants = group["variants"]
        best = max(variants, key=lambda v: (variants[v], len(v)))
        preferred.update({v: best for v in variants if v != best})
    return preferred


def audit_csv(
    path: str,
    gstin_column: str | None = None,
    state_column: str | None = None,
    country_column: str | None = None,
    output_path: str | None = None,
    max_issues: int = 50,
) -> dict:
    """Validate every GSTIN in a CSV and cross-check it against the state column.

    Columns are auto-detected by name ("gstin", "state", "country") when not given.
    If output_path is set, every row is written back out with issue columns added.
    """
    src = Path(path).expanduser()
    with src.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    gstin_column = gstin_column or _find_column(headers, "gstin")
    state_column = state_column or _find_column(headers, "state")
    country_column = country_column or _find_column(headers, "country")
    if not gstin_column or gstin_column not in headers:
        raise ValueError(f"GSTIN column not found; columns are: {headers}")
    for name in (state_column, country_column):
        if name and name not in headers:
            raise ValueError(f"column '{name}' not found; columns are: {headers}")

    counts = Counter()
    issues = []
    state_values, country_values = Counter(), Counter()
    flagged_rows = []

    # Countries have no official list here, so spelling fixes come from the feed itself.
    country_fixes = {}
    if country_column:
        country_values.update(row.get(country_column) or "" for row in rows)
        country_fixes = _preferred_spellings(_spelling_groups(country_values, canonical_country))

    for line_no, row in enumerate(rows, start=2):  # header is line 1
        row_issues, row_warnings = [], []
        raw = row.get(gstin_column) or ""
        if not raw.strip():
            counts["missing_gstin"] += 1
            row_issues.append(("missing_gstin", "GSTIN is empty"))
            result = None
        else:
            result = validate_gstin(raw)
            if not result.valid:
                counts["invalid_gstin"] += 1
                row_issues.append(("invalid_gstin", "; ".join(result.errors)))

        if state_column:
            state_raw = row.get(state_column) or ""
            state_values[state_raw] += 1
            state_code = state_code_for(state_raw)
            if state_raw.strip() and state_code is None:
                counts["unknown_state_value"] += 1
                row_issues.append(("unknown_state_value", f"'{state_raw}' is not a recognised state"))
            elif result and result.state_code and state_code and not codes_match(result.state_code, state_code):
                counts["state_mismatch"] += 1
                row_issues.append((
                    "state_mismatch",
                    f"state column says {STATE_CODES[state_code]} but GSTIN is registered in "
                    f"{result.state or result.state_code}",
                ))
            if state_code and state_raw.strip() != STATE_CODES[state_code]:
                row_warnings.append(("nonstandard_spelling", f"state '{state_raw}' -> '{STATE_CODES[state_code]}'"))

        if country_column:
            country_raw = row.get(country_column) or ""
            if country_raw in country_fixes:
                row_warnings.append(("nonstandard_spelling", f"country '{country_raw}' -> '{country_fixes[country_raw]}'"))

        for kind, detail in row_issues + row_warnings:
            if len(issues) < max_issues:
                issues.append({"line": line_no, "gstin": raw, "issue": kind, "detail": detail})
        flagged_rows.append((row_issues, row_warnings))
        counts["nonstandard_spelling"] += len(row_warnings)
        if row_issues:
            counts["rows_with_issues"] += 1
        elif row_warnings:
            counts["rows_with_warnings_only"] += 1

    report = {
        "file": str(src),
        "rows": len(rows),
        "columns_used": {"gstin": gstin_column, "state": state_column, "country": country_column},
        "summary": {
            k: counts[k]
            for k in (
                "rows_with_issues", "rows_with_warnings_only", "invalid_gstin", "missing_gstin",
                "state_mismatch", "unknown_state_value", "nonstandard_spelling",
            )
        },
        "issues": issues,
        "issues_truncated": sum(len(i) + len(w) for i, w in flagged_rows) > len(issues),
        "inconsistent_spellings": {},
    }
    if state_column:
        report["most_common_states"] = state_values.most_common(5)
        report["inconsistent_spellings"]["state"] = _spelling_groups(
            state_values, lambda v: state_code_for(v) or v.strip().lower()
        )
    if country_column:
        report["inconsistent_spellings"]["country"] = _spelling_groups(country_values, canonical_country)

    if output_path:
        out = Path(output_path).expanduser()
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers + ["audit_status", "audit_issues"])
            writer.writeheader()
            for row, (row_issues, row_warnings) in zip(rows, flagged_rows):
                writer.writerow({
                    **row,
                    "audit_status": "issue" if row_issues else "warning" if row_warnings else "ok",
                    "audit_issues": " | ".join(f"{k}: {d}" for k, d in row_issues + row_warnings),
                })
        report["output_path"] = str(out)

    return report

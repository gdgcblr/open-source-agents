"""MCP server exposing GSTIN validation and CSV audit tools over stdio."""

from collections import Counter

from mcp.server.mcpserver import MCPServer

from . import audit, gstin, states

mcp = MCPServer("gstin-toolkit")


@mcp.tool()
def validate_gstin(gstin_number: str) -> dict:
    """Validate an Indian GSTIN: format, state code, PAN and check digit.

    Returns validity, errors/warnings, the registered state, the embedded PAN
    and its holder type, and the expected check digit (handy for spotting typos).
    """
    return gstin.validate_gstin(gstin_number).to_dict()


@mcp.tool()
def validate_gstins(gstin_numbers: list[str]) -> dict:
    """Validate many GSTINs at once and summarise how many are valid, invalid or repeated."""
    results = [gstin.validate_gstin(g) for g in gstin_numbers]
    repeats = Counter(r.gstin for r in results if r.gstin)
    return {
        "total": len(results),
        "valid": sum(r.valid for r in results),
        "invalid": sum(not r.valid for r in results),
        "unique": len(repeats),
        "repeated": {g: n for g, n in repeats.items() if n > 1},
        "results": [r.to_dict() for r in results],
    }


@mcp.tool()
def lookup_state(code_or_name: str) -> dict:
    """Resolve a GST state code ("29") or a state name/abbreviation ("KA", "Orissa") to both forms."""
    code = states.state_code_for(code_or_name)
    return {"input": code_or_name, "state_code": code, "state": states.STATE_CODES.get(code) if code else None}


@mcp.tool()
def audit_csv(
    path: str,
    gstin_column: str | None = None,
    state_column: str | None = None,
    country_column: str | None = None,
    output_path: str | None = None,
    max_issues: int = 50,
) -> dict:
    """Audit a local CSV feed of GST data.

    Validates every GSTIN, flags rows whose state column disagrees with the state the
    GSTIN is registered in, and lists state/country values spelled more than one way
    (e.g. "UAE" vs "United Arab Emirates"). Columns are auto-detected by name when not
    given. Set output_path to write a copy of the CSV with audit_status (issue/warning/ok)
    and audit_issues columns, including per-row spelling fixes like 'KA' -> 'Karnataka'.
    """
    return audit.audit_csv(path, gstin_column, state_column, country_column, output_path, max_issues)


@mcp.prompt(title="Review a GST feed")
def review_gst_feed(path: str, recipient: str = "the data team") -> str:
    """Audit a GST CSV feed, then summarise the fixes and draft an email asking for them."""
    # Some clients pass file mentions through as "@path/to/file.csv".
    path = path.strip().removeprefix("@")
    return f"""Review the GST data feed at: {path}

1. Call the `audit_csv` tool on that file. Set `output_path` to the same folder with
   "_audited" added before ".csv", so there is an annotated copy to share.
2. Summarise the result for a non-technical reader:
   - Errors to fix (audit_status = issue), grouped by type: invalid GSTIN, missing GSTIN,
     state not matching the GSTIN. For invalid check digits, give the likely corrected GSTIN
     but say it must be confirmed with the supplier.
   - Spellings to standardise (audit_status = warning), as "old -> new" pairs.
   - If one state value dominates `most_common_states` and also appears in the mismatches,
     call it out as a likely default value in the source system.
3. Draft a short, polite email to {recipient} listing only the errors to fix (by line and
   invoice/row identifier where available), mention the annotated CSV, and ask them to
   standardise the spellings in the source. Do not invent issues the audit did not report.
4. Note that the audit checks format and checksums only; it does not confirm a GSTIN is
   currently registered on the GST portal."""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

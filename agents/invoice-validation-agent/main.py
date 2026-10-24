"""Invoice validation agent with deterministic checks and JSON output."""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def validate_invoice(invoice: dict, known_invoices: list | None = None) -> dict:
    """Validate invoice fields, totals, and duplicate identifiers."""
    known_invoices = known_invoices or []
    issues = []

    required = [
        "invoice_number", "vendor", "invoice_date",
        "po_number", "subtotal", "tax", "total"
    ]

    for field in required:
        if invoice.get(field) is None or str(invoice.get(field)).strip() == "":
            issues.append({
                "code": "MISSING_FIELD",
                "field": field,
                "severity": "error",
                "message": f"Required field '{field}' is missing."
            })

    invoice_number = str(invoice.get("invoice_number", "")).strip().casefold()
    vendor = str(invoice.get("vendor", "")).strip().casefold()

    for existing in known_invoices:
        existing_number = str(existing.get("invoice_number", "")).strip().casefold()
        existing_vendor = str(existing.get("vendor", "")).strip().casefold()

        if invoice_number and vendor and invoice_number == existing_number and vendor == existing_vendor:
            issues.append({
                "code": "DUPLICATE_INVOICE",
                "field": "invoice_number",
                "severity": "error",
                "message": "An invoice with this number and vendor already exists."
            })
            break

    try:
        subtotal = Decimal(str(invoice["subtotal"]))
        tax = Decimal(str(invoice["tax"]))
        total = Decimal(str(invoice["total"]))

        if not all(value.is_finite() and value >= 0 for value in (subtotal, tax, total)):
            raise InvalidOperation

        if (subtotal + tax).quantize(Decimal("0.01")) != total.quantize(Decimal("0.01")):
            issues.append({
                "code": "TOTAL_MISMATCH",
                "field": "total",
                "severity": "error",
                "message": "Subtotal plus tax does not equal the stated total."
            })
    except (KeyError, InvalidOperation, ValueError, TypeError):
        if not any(issue["field"] in {"subtotal", "tax", "total"} for issue in issues):
            issues.append({
                "code": "INVALID_AMOUNT",
                "field": "subtotal/tax/total",
                "severity": "error",
                "message": "Amounts must be valid, non-negative decimal numbers."
            })

    return {
        "invoice_number": invoice.get("invoice_number"),
        "vendor": invoice.get("vendor"),
        "status": "REJECTED" if issues else "APPROVED",
        "issue_count": len(issues),
        "issues": issues,
        "approval_note": (
            "Automated checks passed; this is not authorization to pay."
            if not issues else
            "Resolve the reported issues before considering approval."
        )
    }


def sample_invoices() -> dict:
    """Return reproducible demo cases."""
    valid = {
        "invoice_number": "INV-1001",
        "vendor": "Acme Supplies",
        "invoice_date": "2026-10-24",
        "po_number": "PO-2001",
        "subtotal": "1000.00",
        "tax": "180.00",
        "total": "1180.00"
    }

    duplicate = {**valid}
    mismatch = {
        **valid,
        "invoice_number": "INV-1002",
        "total": "1200.00"
    }

    return {
        "valid": {"invoice": valid, "known_invoices": []},
        "duplicate": {"invoice": duplicate, "known_invoices": [valid]},
        "mismatch": {"invoice": mismatch, "known_invoices": []}
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="InvoiceGuard validation agent")
    parser.add_argument(
        "--case",
        choices=["valid", "duplicate", "mismatch"],
        default="mismatch",
        help="Select a built-in demonstration case."
    )
    parser.add_argument("--input", type=Path, help="Optional path to invoice JSON.")
    args = parser.parse_args()

    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        data = sample_invoices()[args.case]

    result = validate_invoice(
        data["invoice"],
        data.get("known_invoices", [])
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

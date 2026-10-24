"""Invoice validation agent with deterministic checks and JSON output."""

import argparse
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


def validate_invoice(invoice: dict, known_invoices: list | None = None) -> dict:
    """Validate invoice fields, totals, and duplicate identifiers."""
    if not isinstance(invoice, dict):
        return _input_error("Invoice must be a JSON object.")
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

    raw_date = invoice.get("invoice_date")
    if raw_date not in (None, ""):
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw_date)):
                raise ValueError
            date.fromisoformat(str(raw_date))
        except ValueError:
            issues.append({"code": "INVALID_DATE", "field": "invoice_date", "severity": "error",
                           "message": "Invoice date must be a valid calendar date in YYYY-MM-DD format."})

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

    arithmetic_facts = None
    try:
        subtotal = Decimal(str(invoice["subtotal"]))
        tax = Decimal(str(invoice["tax"]))
        total = Decimal(str(invoice["total"]))

        if not all(value.is_finite() and value >= 0 for value in (subtotal, tax, total)):
            raise InvalidOperation

        expected_total = (subtotal + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        stated_total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        arithmetic_facts = {
            "subtotal": _money(subtotal),
            "tax": _money(tax),
            "expected_total": _money(expected_total),
            "stated_total": _money(stated_total),
            "signed_difference": _money(stated_total - expected_total),
        }
        if expected_total != stated_total:
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

    result = {
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
    if arithmetic_facts is not None:
        result["verified_arithmetic"] = arithmetic_facts
    return result


def _money(value: Decimal) -> str:
    """Format a Decimal fact without allowing the model to do arithmetic."""
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def _input_error(message: str) -> dict:
    return {"status": "REJECTED", "issue_count": 1, "issues": [{
        "code": "INVALID_INPUT", "field": "input", "severity": "error", "message": message
    }], "approval_note": "The input could not be validated; no payment decision was made."}


def load_input(path: Path) -> dict:
    """Load the CLI envelope and return a predictable result for bad files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return _input_error(f"Unable to read input file: {type(exc).__name__}.")
    except json.JSONDecodeError:
        return _input_error("Input file is not valid JSON.")
    if not isinstance(data, dict) or not isinstance(data.get("invoice"), dict):
        return _input_error("Input must contain an 'invoice' JSON object.")
    known = data.get("known_invoices", [])
    if not isinstance(known, list) or not all(isinstance(item, dict) for item in known):
        return _input_error("'known_invoices' must be a list of JSON objects.")
    return validate_invoice(data["invoice"], known)


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
    parser.add_argument("--explain", action="store_true", help="Request an optional AI explanation.")
    parser.add_argument("--provider", choices=["ollama", "gemini"], help="AI provider (requires --explain).")
    args = parser.parse_args()

    if args.input:
        result = load_input(args.input)
    else:
        data = sample_invoices()[args.case]
        result = validate_invoice(data["invoice"], data.get("known_invoices", []))
    if args.explain:
        from providers import explain_result
        invoice = data.get("invoice", {}) if args.input is None else {}
        result["ai_explanation"] = explain_result(invoice, result, args.provider)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

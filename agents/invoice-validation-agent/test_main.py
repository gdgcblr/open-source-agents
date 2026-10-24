from main import sample_invoices, validate_invoice


def test_valid_invoice_passes():
    data = sample_invoices()["valid"]
    result = validate_invoice(data["invoice"], data["known_invoices"])
    assert result["status"] == "APPROVED"
    assert result["issues"] == []


def test_duplicate_invoice_is_rejected():
    data = sample_invoices()["duplicate"]
    result = validate_invoice(data["invoice"], data["known_invoices"])
    assert result["status"] == "REJECTED"
    assert any(issue["code"] == "DUPLICATE_INVOICE" for issue in result["issues"])


def test_total_mismatch_is_rejected():
    data = sample_invoices()["mismatch"]
    result = validate_invoice(data["invoice"], data["known_invoices"])
    assert result["status"] == "REJECTED"
    assert any(issue["code"] == "TOTAL_MISMATCH" for issue in result["issues"])


def test_missing_required_field_is_detected():
    invoice = sample_invoices()["valid"]["invoice"].copy()
    invoice["po_number"] = ""
    result = validate_invoice(invoice)
    assert any(issue["code"] == "MISSING_FIELD" for issue in result["issues"])

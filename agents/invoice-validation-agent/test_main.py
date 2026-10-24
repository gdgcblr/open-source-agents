from main import sample_invoices, validate_invoice
from providers import explain_result


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
    assert result["verified_arithmetic"] == {
        "subtotal": "1000.00", "tax": "180.00", "expected_total": "1180.00",
        "stated_total": "1200.00", "signed_difference": "20.00"
    }


def test_missing_required_field_is_detected():
    invoice = sample_invoices()["valid"]["invoice"].copy()
    invoice["po_number"] = ""
    result = validate_invoice(invoice)
    assert any(issue["code"] == "MISSING_FIELD" for issue in result["issues"])


def test_ai_is_disabled_without_provider():
    explanation = explain_result({}, {"status": "APPROVED"}, None)
    assert explanation["status"] == "fallback"
    assert "Status remains APPROVED" in explanation["text"]


def test_missing_gemini_configuration_is_graceful(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    explanation = explain_result({}, {"status": "REJECTED"}, "gemini")
    assert explanation["status"] == "fallback"


def test_ollama_failure_is_graceful(monkeypatch):
    import providers
    def fail(*args):
        raise OSError("offline")
    monkeypatch.setattr(providers, "_call_ollama", fail)
    explanation = explain_result({}, {"status": "REJECTED"}, "ollama")
    assert explanation["status"] == "fallback"


def test_provider_explanation_is_separate_and_status_unchanged(monkeypatch):
    import providers
    monkeypatch.setattr(providers, "_call_ollama", lambda invoice, result: "The TOTAL_MISMATCH means the stated total is incorrect; review the mismatch.")
    result = validate_invoice(sample_invoices()["mismatch"]["invoice"])
    explanation = explain_result({}, result, "ollama")
    assert result["status"] == "REJECTED"
    assert explanation["status"] == "generated"
    assert result["status"] == "REJECTED"
    assert any(issue["code"] == "TOTAL_MISMATCH" for issue in result["issues"])


def test_contradictory_ai_output_uses_verified_fallback(monkeypatch):
    import providers
    monkeypatch.setattr(providers, "_call_ollama", lambda invoice, result: "1000 plus 180 results in 1200, so the invoice is fine.")
    result = validate_invoice(sample_invoices()["mismatch"]["invoice"])
    explanation = explain_result({}, result, "ollama")
    assert explanation["status"] == "fallback"
    assert "expected total 1180.00" in explanation["text"]
    assert result["status"] == "REJECTED"

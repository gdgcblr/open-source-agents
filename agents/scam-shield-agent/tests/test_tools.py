import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from scam_shield.tools import (  # noqa: E402
    analyze_links,
    detect_payment_requests,
    rules_verdict,
    scan_scam_patterns,
)


def test_fake_brand_domain_is_flagged():
    links = analyze_links("Update KYC at https://sbi-kyc-update.xyz/login", follow_shorteners=False)["links"]
    assert any("sbi" in f for f in links[0]["flags"])
    assert any(".xyz" in f for f in links[0]["flags"])


def test_homoglyph_lookalike_is_flagged():
    for text in ("visit paytrn.com/claim", "pay at amaz0n-delivery.in"):
        assert analyze_links(text, follow_shorteners=False)["risk_points"] >= 45, text


def test_official_domains_are_not_flagged():
    result = analyze_links("Track at amazon.in/orders or onlinesbi.sbi", follow_shorteners=False)
    assert result["risk_points"] == 0
    assert all(link["is_known_official_domain"] for link in result["links"])


def test_email_is_not_treated_as_link_or_upi():
    assert analyze_links("mail ravi.k@gmail.com", follow_shorteners=False)["links"] == []
    assert detect_payment_requests("mail ravi.k@gmail.com")["upi_ids"] == []


def test_payment_traps():
    result = detect_payment_requests("Scan the QR to receive money and enter your UPI PIN. UPI: help@ybl")
    names = {s["signal"] for s in result["signals"]}
    assert {"asks_for_upi_pin", "receive_money_trap"} <= names
    assert result["upi_ids"] == ["help@ybl"]


def test_patterns_include_indian_languages():
    assert scan_scam_patterns("आपका खाता बंद हो जाएगा, तुरंत करें")["risk_points"] > 0


def test_verdicts():
    assert rules_verdict("Congratulations you have won the KBC lottery, pay registration fee",
                         follow_shorteners=False)["verdict"] == "scam"
    assert rules_verdict("Meeting moved to 4 pm tomorrow", follow_shorteners=False)["verdict"] == "safe"


def test_api_falls_back_to_rules_without_key(monkeypatch):
    import server

    # Importing server runs load_dotenv(), which would restore a real key from .env,
    # so disable AI after the import; otherwise this test calls Gemini.
    monkeypatch.setattr(server, "_ai_enabled", lambda: False)
    client = TestClient(server.app)
    res = client.post("/api/check", json={"text": "Share the OTP to stop your account being blocked"})
    assert res.status_code == 200
    assert res.json()["mode"] == "rules"
    assert res.json()["verdict"] in ("scam", "suspicious")
    assert client.post("/api/check", json={"text": ""}).status_code == 400
    assert client.get("/").status_code == 200


def test_family_new_number_with_money_request():
    names = lambda text: {c["category"] for c in scan_scam_patterns(text)["categories"]}  # noqa: E731
    assert "new_number_money_request" in names("Hi Dad, my new number. Please send money for the fee")
    assert "new_number_money_request" in names("Ye mera naya number hai, 2000 paise bhej do")
    assert "new_number_money_request" not in names("This is my new number, save it")


def test_romanised_hindi_patterns():
    found = {c["category"] for c in scan_scam_patterns(
        "Aapki bijli kaat di jayegi, khata band hoga, turant call karo")["categories"]}
    assert {"utility_disconnection", "account_block_kyc", "urgency_pressure"} <= found


def test_short_keywords_match_whole_words_only():
    assert scan_scam_patterns("Your train leaves at 6")["risk_points"] == 0
    assert scan_scam_patterns("TRAI notice: your number will be cut")["risk_points"] > 0


def test_otp_advice_and_credited_refunds_are_not_flagged():
    assert detect_payment_requests("OTP 1234. Do not share OTP with anyone")["signals"] == []
    assert scan_scam_patterns("Refund of Rs 300 has been credited to your card")["risk_points"] == 0
    assert detect_payment_requests("Please share the OTP now")["signals"]

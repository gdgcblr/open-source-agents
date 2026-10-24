# 03 — Deterministic rental analysis & risk

**Implement:**
- `listing_parser.py` — extract locality, rent, deposit, BHK, furnishing from text
- `risk_rules.py` — rule IDs RF-001..RF-012 (payment pressure, OTP, third party, contradictions, etc.)
- `detect_rental_red_flags` + `analyze_rental_listing` tools
- `generate_rental_safety_report` aggregator

**Tests:** `tests/test_risk_rules.py`, `tests/test_listing_parser.py`

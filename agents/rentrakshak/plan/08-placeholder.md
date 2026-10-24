# 08 — Guardrails & Model Armor (optional)

**Implement:**
- `content_safety.py` — prompt-injection patterns, secret detection, PII patterns, harassment keywords
- Sanitize listing/chat before agent context; refuse instruction override from untrusted content
- `model_armor.py` — optional GCP client; graceful no-op when unset

**Tests:** `tests/test_guardrails.py`

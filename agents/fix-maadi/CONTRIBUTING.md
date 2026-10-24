# Extending Fix Maadi

Fix Maadi is intentionally built as a small, replaceable agent core rather than a Bengaluru-only hard-coded application.

## What contributors can add

### 1. City or authority packs

Add a source-linked registry under `data/` for another city. Each channel should include:

- category and responsible authority
- official source URL
- intended use and scope warnings
- required evidence or fields
- verification date
- a safe handoff mode

Do not add scraped, private, or unverified contact details.

### 2. Issue packs

Add a rule with keywords, evidence checklist, severity guidance, bilingual labels, and an evaluation scenario. Include a regression test for false positives.

### 3. Model providers

Add a provider behind the existing vision boundary. It must:

- return the supported category schema
- validate model output before routing
- preserve the deterministic fallback
- never invent authority, SLA, location, or contact details
- add a provider test using a mocked response

### 4. Channel adapters

Add an adapter in `adapters.py` only when the destination is official and its behavior is documented. Adapters prepare a reviewable action; they do not submit, bypass login/OTP/CAPTCHA, or transmit data without resident approval.

### 5. Languages and accessibility

Contribute Kannada, transliteration, voice input, screen-reader labels, keyboard navigation, and high-contrast improvements without changing the routing contract.

### 6. Evaluation and safety

Every new category or channel should add an offline scenario under `evals/scenarios.json`. New model or external-action behavior should add a guardrail and a failure test.

## Review checklist

- `python -m unittest discover -s tests -v`
- `python evals/run_evals.py`
- no secrets or personal data
- source links and verification dates included
- no unsupported guarantees
- no automatic external submission
- only files inside the relevant project directory changed

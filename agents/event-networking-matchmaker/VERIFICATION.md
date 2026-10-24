# Verification record — 24 October 2026

## Environment and reproducibility

Tested on macOS ARM64 with Python 3.14.5. A newly created virtual environment installed only `requirements-dev.txt`, passed the complete test suite, and reported `No broken requirements found` from `pip check`. Browser behavior was checked in the Codex in-app browser. JavaScript passed `node --check static/app.js`.

Python 3.11–3.13, Windows/Linux, real mobile devices, HTTPS reverse-proxy hosting, and production traffic have not been independently verified in this session.

## Automated tests

`python -m pytest -q`: **36 passed** in 2.40 seconds in the clean environment. One upstream Starlette warning notes that its httpx TestClient integration is deprecated; tests still pass with the declared pinned dependencies.

Coverage includes the original open-source query regression, profile evidence, interest-versus-skill labels, relevant-offers filtering, aliases/paraphrases, consent exclusions, malformed files, event isolation, token revocation, withdrawal suppression, check-in expiry, organizer deletion, bounded uploads, trusted hosts, 24 requests across independent synthetic sessions, 200-profile catalogs, semantic failure fallback, and mocked Gemini tool boundaries. A blank goal is explicitly tested to ensure stored profile needs are never sent to the cloud planner.

## Retrieval evaluation

`python evaluate.py`: **10/10 curated synthetic cases passed** using local lexical NLP. A case passes when all specified expected IDs occur in the top three, or an unrelated query returns nothing. This does not establish general accuracy, precision, or a held-out benchmark result; the examples overlap the documented domain phrase map.

| Query | Actual returned IDs |
| --- | --- |
| I want to know how I can start contributing to open source | P012, P011, P002 |
| I need help with my first pull request | P011, P002, P012 |
| I want to put my app online | P003, P002, P013 |
| I want to run AI offline | P006, P007, P010 |
| Docker | P003 |
| I am working on a campus map | P016, P015 |
| I need help with documentation | P011 |
| I need help with a screen reader | P002, P005 |
| I want to build a mobile app | P002, P003, P015 |
| quantum spectroscopy | No matches |

Ten sequential searches over a 200-profile synthetic catalog: median **10.02 ms**, maximum **10.79 ms** for the local workflow in the development environment. This excludes HTTP/browser overhead and is not a 200-concurrent-user load test. Timings vary by machine and installed engine.

## Browser walkthrough

Verified sample login as Arun; the original full-sentence open-source query returned Kiran, Farah, and Priya. Kiran/Farah showed related offered skills; Priya showed shared-interest evidence and an explicit non-expertise caveat. The offered-skills-only filter returned Kiran and Farah. Profile evidence and the actual local workflow trace expanded successfully, and the browser reported no JavaScript errors during these checks.

In a second browser tab, Kiran checked in at Table B. Arun's available-now query returned Kiran with Table B and an expiry time. The in-app organizer/attendee guide opened successfully. `sample/app-desktop.jpg` records actual synthetic results from this walkthrough.

## Explicitly unverified components

- **Live MiniLM inference:** the optional integration and setup command are implemented, but the model-weight download was slow and cancelled. Missing-model and runtime-error fallbacks are tested. Do not present semantic quality as validated until running `python evaluate.py --model-dir ...` with a successfully installed model.
- **Live Gemini provider:** tool-calling requests, privacy boundaries, call limits, and fallbacks are tested with mocked HTTP only. No authorized live key was available. Verify against the configured model/account before relying on this optional mode.
- No formal security audit, penetration test, legal-compliance certification, or real-event outcome study was performed.

The reliable no-key submission path is the tested local lexical NLP workflow. The UI identifies that engine honestly.

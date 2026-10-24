# Security and privacy design

## Scope and trust boundary

The organizer controls the server, source response spreadsheet, hosting, and retention policy. Attendees are authenticated within one event. Organizer access is privileged. This is a small event application, not an audited multi-tenant identity platform.

## Data minimization

The importer retains only stable attendee ID, display name, offered skills, needs, interests, project, and networking window for explicitly consenting rows. Unknown columns—including email—are discarded. Sensitive text placed inside a recognized field is not automatically redacted; organizers should keep these fields appropriate for participant visibility.

Only new private tokens are returned once to an authenticated organizer. SQLite stores their SHA-256 hashes, not plaintext. Tokens have cryptographic random entropy. Public badge IDs cannot authenticate. Optional email invitations put the token in a URL fragment, which is cleared immediately and is not sent in the initial HTTP request. The full invitation remains sensitive to email providers, scanners, forwarding and browser extensions. Tokens are not placed in URL query parameters, cookies, localStorage, or browser analytics. User goals and profile vectors are not written to the database. See DEPLOY.md for invitation limitations.

## Matching privacy

Local lexical NLP makes no provider calls. Local semantic inference reads a preinstalled model directory with offline loading. Hugging Face and ONNX telemetry are disabled before model inference. Model setup downloads public files without reading attendee data.

The optional Gemini planner receives the user’s typed request and aggregate hit counts only. It cannot fetch or export profiles. Tool names, arguments, call counts, and search scope are validated. Only `search_people` and `finish` are executable; searches are constrained to already-eligible candidates, and model-suggested queries cannot introduce candidates unsupported by the original local retrieval. No model-generated biography, expertise claim, or location is displayed.

Each response rechecks the requester and returned profiles after potentially slow model work. Withdrawn or changed profiles are removed and locations are refreshed. No cross-request vector/profile cache can retain withdrawn data. A small unavoidable race can still exist between the final database read and network delivery; previously delivered information cannot be recalled from another attendee’s browser.

## Access and application protections

- Organizer-only import, token rotation, and event deletion; per-event attendee bearer tokens.
- Reassigning an ID to a different display name revokes the old token and clears location/met state.
- Explicit opt-in; withdrawal markers prevent stale exports from recreating a withdrawn identity.
- Expiring meeting-spot presence and voluntary checkout; no GPS or background location collection.
- Bounded request bodies, including chunked uploads; XLSX compressed/expanded size, row, column, and field bounds; formulas rejected.
- Parameterized SQL, text-node browser rendering, no external scripts, same-origin checks, trusted host validation, and no-store headers on normal responses.
- Per-token in-memory rate limiting; no claims of distributed or sophisticated abuse prevention.
- Unix database permissions restricted to the current user; SQLite secure deletion enabled. These do not encrypt disks or external backups.

## Retention and withdrawal

Attendee withdrawal removes their profile, presence and met relationships, retaining an event/ID suppression marker. Organizer event deletion removes all event records, including suppression markers. Source Forms/Sheets, exported workbooks, downloaded tokens, screenshots and backups remain outside this control. Organizers must manage those separately according to the policy they communicated.

## Deployment requirements

Use HTTPS with the exact permitted hostname, private persistent storage, a protected organizer key, and restricted backend exposure. Trust proxy headers only from your configured reverse proxy. Separate sample and real databases, and never enable sample mode against a real attendee dataset. Protect downloaded token exports and verify identity before replacing tokens.

## Residual risks

Bearer tokens can be shared or stolen. Authenticated attendees can copy the profiles they see. Organizers can inspect their database. Similarity scores may be wrong, biased, or manipulated by exaggerated profiles. Public event names are visible before login. This version has no verified identity provider, role delegation, distributed throttling, encryption-at-rest management, or formal penetration test. Tests demonstrate specific implemented protections, not a blanket guarantee of security or legal compliance.

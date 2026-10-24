# Initial test record

Run date: 24 October 2026. Host: macOS, ARM64. Python: 3.12.3.
Locked ADK version: 2.13.0 (ADK 2.x).

| Check | Result |
|---|---|
| Automated tests | 78 passed |
| Clean project setup | New environment installed from uv.lock; 71 tests and helper build passed |
| Local setup scripts | Settings preserved, only missing models downloaded, and local Web launch verified with stubs |
| Actual local launch | `sh scripts/run-local.sh` started ADK Web; a live `/run` request returned 9 Calendar events without a helper error |
| Ruff checks | Passed |
| Python source package and wheel | Built |
| Native Calendar/Contacts helper | Compiled and ad-hoc signed |
| Compose configuration | Valid |
| Docker image build/run | Not tested: local Docker engine is not running |
| Real Mail reads | 8 of 12 messages read; 4 slow messages reported separately; partial coverage |
| Real Calendar reads | 12 events over 14 days; valid IDs/dates; 9 all-day events |
| Real Contacts reads | Skipped by user request; earlier access was denied |
| Real app writes | Not tested; no messages or contacts were changed |
| Live Gemma extraction | 8/8 synthetic cases passed |
| Live ADK chat | Correct synthetic subscription total and matched bill status |
| Live EmbeddingGemma | Installed embeddinggemma-2:740m returned 768-dimensional vectors |
| Real email extraction | Completed on the sample; no financial candidates found |
| Persistent memory | Save, reopen, and delete checks passed in an isolated test directory |
| Local bridge | Authentication, model proxy, Calendar reads, and synthetic ADK chat passed |
| Local semantic search | Cached sources indexed; returned source links validated |

The extraction run used `gemma4:e4b`, model ID `c6eb396dbd59`, on the local GPU.
Its eight cases took 29.02 seconds in total; first-case model loading affects timing.
The initial prompt passed 4/8. The revised prompt uses examples, required output fields,
and disabled thinking. It passed 8/8 on the same development set. This is not a held-out
accuracy estimate or a guarantee for real emails. Full synthetic outputs and settings
are in [evals/baseline.json](evals/baseline.json).

LiteLLM is pinned to 1.106.2. Its optional MCP handler is skipped because this app uses
local Python tools. The live chat test verifies that path without the MCP proxy extras.

## Covered behaviour

- Exact decimal totals, month boundaries, currencies, refunds, and duplicate references.
- Partial/split payments; mismatched cards, statement periods, issuers, and currencies.
- Conflicting statements and ambiguous duplicates require review.
- Unsupported tools, extra arguments, expired approvals, and reused requests fail.
- Denied host approval prevents the native app call.
- Connector authentication, browser-origin rejection, and local-model restrictions.
- Source evidence checks; changed/deleted source records invalidate dependent records/vectors.
- Persistent preferences, keyword/vector retrieval, ADK tool execution, and SQLite sessions.
- Mail read limits apply before content fetch; successful messages survive later timeouts.
- Each Mail message has a 12-second limit; the scan stops after 120 seconds.
- Synthetic model extraction includes renewal notices, incomplete data, and injected instructions.

The real email sample contained no extracted financial records. Real bill/payment matching
and real subscription totals remain unverified. No records were auto-accepted. Source text,
vectors, and any candidates stay in ignored local storage; this report contains no email
subjects, addresses, amounts, event titles, or contact details. The live model proxy test
used synthetic financial records. Contacts and live app writes were not called in this pass.

The actual launcher check found an invalid placeholder in `MIGINE_MAC_HELPER`. Setup
and launch now repair missing/invalid helper paths and export the checked path to ADK Web.
Regression tests cover unset, valid custom, and invalid helper paths. The live check used
the real local server and Calendar; no Contacts requests or app write actions ran.

Later system diagnostics identified Calendar requests launched from VS Code being
blocked because the responsible app lacks a required Calendar entitlement. The same
helper succeeds from the Codex test process. Use the macOS Terminal app for local app
access. Tests now cover safe native failure/timeout diagnostics, bridge propagation,
and ADK returning unavailable Calendar data without crashing. Raw native stderr is not
shown to the model or browser.

The clean setup check copied only staged project files, created a new Python environment,
and installed locked dependencies from the local uv cache. It did not copy private data,
local configuration, or the existing virtual environment.

## First test with Mac apps

1. Follow README setup and use a separate test data directory.
2. Grant each app permission separately. Deny one request and check that the command fails safely.
3. Read a small Inbox batch: `migine sync --since YYYY-MM-DD --limit 5`.
4. Run `extract` and compare every candidate with its source email. Reject wrong fields.
5. Accept correct records. Compare the monthly report with the source statements manually.
6. Search for a test contact, then propose a name/email change. Deny it and verify no change.
7. Propose a flag change on a test email. Approve it once and check the flag in Mail.
8. Repeat the same request ID. It must fail. Test an expired request too.
9. Test Calendar events, recurring events, all-day birthdays, and time-zone boundaries.
10. Start Docker's engine, build the image, and repeat synthetic/connector tests. Check that
    the non-root container can read the mounted secret and retain its data volume.

Use prepared test contacts and messages for write checks. No live write test has run.
Do not claim complete spending coverage, verified sender authenticity, or bank settlement.

## Optional synthetic demo

Use a separate directory for fixtures. This does not import personal email.

```sh
MIGINE_DATA_DIR=./demo uv run migine demo --month 2026-10
MIGINE_DATA_DIR=./demo uv run migine summary --month 2026-10
MIGINE_DATA_DIR=./demo uv run adk web examples/web --host 127.0.0.1 --port 8000 --max_llm_calls 8
```

Open localhost:8000, select `migine_web`, and ask for October 2026 bills and subscriptions.
Expected fixture totals: one INR 12,450.00 statement with matched payment evidence and
INR 279.00 in subscriptions. Only the financial records are synthetic; Calendar and app
tools still access your Mac. Keep fixture and personal data directories separate.

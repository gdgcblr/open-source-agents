# Meeting Assistant Flow

> Prepare a meeting, find suitable times, and explicitly approve every calendar invitation.

## Overview

### Problem statement and intended users

Organizers often switch between chat, calendars, and documents to arrange a meeting. This Flask assistant combines meeting details, free/busy checks, agenda preparation, and a final invitation preview. Existing meetings' titles and agendas are never retrieved.

### Key features

- Real Google account sign-in, separate availability consent, and additional scheduling consent.
- One chat window contains the draft, per-calendar check results, suggested slots, edits, and invitation approval. Account settings are collapsed below it. Refreshing or starting a new chat clears ordinary chat drafts and invitees while preserving login and Calendar consent. Uncertain calendar operations are retained for reconciliation.
- Gemini understands conversational availability questions, slot searches, and scheduling requests, asks for missing dates/emails, and calls a read-only scheduling tool that queries Google Calendar and the MCP slot calculator. No model can approve or send an invitation.
- Editable meeting drafts with attendees, dates, timezone, duration, working hours, and an optional weekend search.
- A local MCP tool calculates up to six exact slots from anonymous busy intervals.
- Google ADK + Gemini automatically drafts a description and agenda from the meeting name. Missing keys or provider failure use an explicitly labeled basic template.
- A separate read-only preview lists the exact title, invitees, time, purpose, and agenda before submission.
- Backend approval/version checks, immediate availability rechecks, and stable Google event IDs prevent blind duplicate creation.
- Unknown attendee availability is explicit and requires acknowledgement.
- Sanitized terminal logs show progress without credentials, participant addresses, agendas, or calendar schedules.

## Technical stack

- Python 3.12, Flask, HTML/CSS, and a small local progress script.
- Google ADK, Gemini API, and the MCP Python SDK.
- Google Calendar API, Google OpenID Connect/OAuth, and OS credential storage through `keyring`.
- SQLite for account records, draft versions, sessions, consent attempts, and operation status.

## Architecture and data flow

```text
Browser -> Flask validation and authenticated workflow
                |-> ADK + Gemini -> editable agenda proposal
                |-> Google free/busy -> anonymous intervals -> local MCP -> slots
                |-> exact invitation preview -> user approval -> conflict recheck
                                                        -> Google event creation
```

The conversational agent can call only its read-only availability/scheduling tool. It cannot create events or approve invitations. Flask coordinates the deterministic MCP slot tool and controls all calendar writes. Only the owner can read/update a draft. No background task sends invitations.

Important files:

- `app.py`: Flask setup, Google account/Calendar consent, and own-calendar checks.
- `chat.py`: basic request parser used only when Gemini is not configured. Natural language uses the ADK agent in agent.py.
- `meetings.py`: draft, agenda, slot, preview, approval, and reconciliation routes.
- `auth.py`: OAuth, PKCE, nonce and identity verification, required-scope checks.
- `calendar_api.py`: free/busy, approved event creation, and minimal lookup of app-generated event IDs.
- `guardrails.py`: sensitive-input checks and meeting/model-context validation.
- `scheduling.py`, `mcp_server.py`, `mcp_client.py`: local slot calculation and its MCP transport.
- `agent.py`: one constrained ADK agenda agent with a bounded run and structured output.
- `storage.py`: owner-scoped SQLite operations, version checks, and atomic creation claims.

## Prerequisites

- Python 3.12 and pip.
- A Google account, Google Cloud project, and OAuth **Web application** client.
- A working OS credential store: macOS Keychain, Windows Credential Locker, or Linux Secret Service.
- Optional Gemini API key for AI agenda generation. Manual scheduling does not require it.

## Installation and setup

From the repository root:

```sh
cd agents/meeting-assistant-flow
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
python -c "from secrets import token_hex; from dotenv import set_key; set_key('.env', 'FLASK_SECRET_KEY', token_hex(32))"
```

Generate the Flask secret once. Changing it signs out existing browsers. On Windows, use `py -3.12 -m venv .venv`, `.venv\Scripts\activate`, and copy `.env.example` without overwriting existing local settings.

### Google sign-in and availability

1. Select or create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Configure **Google Auth Platform -> Branding** with an app name and support/contact email.
3. For personal Gmail testing, choose **External**, keep the app in **Testing**, and add your account under **Audience -> Test users**.
4. Create an OAuth **Web application** client under **Clients** with this exact authorized redirect URI:

   ```text
   http://127.0.0.1:5000/oauth/callback
   ```

5. Download the client JSON as `credentials.json` in this project folder. Keep it out of chat and Git. Its top-level object must be `web`.
6. Enable **Google Calendar API** in the same project as this OAuth client.
7. Under **Data Access**, add:

   ```text
   https://www.googleapis.com/auth/calendar.events.freebusy
   ```

8. Run the app, sign in, click **Connect Google Calendar**, and choose the same Google account. Tokens are saved in the OS credential store after subject and grant verification.

### Enable scheduling

Add this additional scope under **Google Auth Platform -> Data Access**:

```text
https://www.googleapis.com/auth/calendar.events.owned
```

Click **Enable scheduling** in the app and approve the separate Google consent request. This provider permission allows viewing, creating, changing, and deleting events on calendars you own. The application itself restricts its use to approved creations and minimal reference checks of its own generated event IDs. It does not list, modify, or delete existing meetings.

The client JSON and callback do not change. Google account selection, consent, or OS keychain prompts must be completed by the user. Partial grants and a different Google account are rejected. Apps in Google's Testing status may require reconnection after seven days because refresh tokens expire.

### Optional Gemini setup

Create a key through [Google AI Studio](https://aistudio.google.com/api-keys). Save it only in the local `.env`:

```dotenv
GOOGLE_API_KEY=your_actual_key_saved_locally
GEMINI_MODEL=gemini-flash-latest
```

Restart Flask after changing `.env`. Gemini availability, quota, billing, and pricing depend on your account. The planning UI explains that Gemini receives the conversation with email addresses replaced by placeholders. The agent must call its read-only scheduling tool for availability answers. The optional revision endpoint still requires explicit sharing consent. For conversational scheduling, Gemini receives the chat with email addresses replaced by placeholders, supplied dates/times and names, and the read-only tool’s anonymous busy intervals, slot suggestions, and access status. Google credentials and existing event details are excluded. The separate agenda-revision endpoint sends only its selected draft text and instruction; free text may still contain personal information you enter.

Official references: [Google OAuth/OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect), [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth), [ADK MCP tools](https://adk.dev/tools-custom/mcp-tools/).

## Configuration and environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `FLASK_SECRET_KEY` | Yes | None | Random local session-signing secret, at least 32 characters |
| `GOOGLE_CLIENT_CONFIG` | For Google access | `credentials.json` | Server-only OAuth web-client file |
| `GOOGLE_REDIRECT_URI` | No | `http://127.0.0.1:5000/oauth/callback` | Must exactly match the registered Google callback |
| `GOOGLE_API_KEY` | Only for AI agenda | None | Gemini credential, never entered in the chatbot |
| `GEMINI_MODEL` | No | `gemini-flash-latest` | Model available to your Gemini account |

## How to run

```sh
source .venv/bin/activate
python app.py
```

Open `http://127.0.0.1:5000`. Keep the terminal open for progress logs. Restart with Ctrl+C followed by `python app.py` after code or environment changes; debug/reload is disabled.

1. Sign in and connect Calendar. Enable scheduling when ready to create events.
2. With Gemini configured, ask **Is Alex free tomorrow at 3 PM?**, **What slots are available for Alex tomorrow?**, or **Schedule a project call with Alex tomorrow at 3 PM**. Supply Alex’s email when asked. Click **Send message** for each turn. Without Gemini, use **Meeting name on YYYY-MM-DD with email** for basic planning.
3. The app automatically prepares description/agenda and checks your calendar plus permitted attendee calendars through the MCP slot tool. Defaults are 30 minutes, 9 AM–5 PM, Asia/Kolkata, including the selected day on weekends. Unknown calendars are not assumed free.
4. Review the filled details. **Edit meeting details** changes any default, title, agenda, or attendee. Saving automatically refreshes slots. Choose **Start another meeting** for a new request.
5. Select a slot and click **Review invitation**. Nothing is sent yet.
6. Review all details and recipient addresses. Acknowledge unknown availability if applicable.
7. Explicitly approve the invitation and click **Create meeting and send invitations**.
8. After Google's confirmation, open the event link. Invitation creation does not imply attendee acceptance or guarantee email delivery.

Saving any edit or generating an agenda clears old slot suggestions and review approval. Slot suggestions expire after 30 minutes. Submitted/uncertain invitations are immutable; retries reuse the same event ID.

## Example input and output

Synthetic automated end-to-end example (no real invitations sent):

```text
Title: Project kickoff
Purpose: Agree on scope and responsibilities
Attendees: invitee@example.test
Duration: 30 minutes
Timezone: Asia/Kolkata
Agenda: Goals — 5 min; Scope — 15 min; Responsibilities — 10 min

Plan meeting (automatic agenda and slot search) -> Select a suggested 10:00–10:30 slot
Review -> Approve exact invitation -> synthetic provider confirms creation
Repeating confirmation -> no second creation request
```

A real MCP subprocess test returns six slots for a valid future range. The actual ADK runner is tested with a synthetic offline model returning a structured time-boxed agenda. Neither test is presented as a real Gemini result.

Live Google sign-in and a read-only free/busy request have been verified in the user's configured environment. Live Gemini generation, expanded scheduling consent, and actual invitation creation remain unverified; no real invitation is sent as part of automated verification.

## How to test

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
```

The suite uses synthetic identities, a mock OS keychain, and fake calendar writes. It includes a real MCP subprocess and the real ADK runner with an offline synthetic model. It covers OAuth identity claims/signatures, PKCE, nonce/state replay, browser/account binding, CSRF, token isolation, private-data boundaries, timezone/overlap rules, unknown availability, exact approval/version checks, conflict rechecks, duplicate submissions, and uncertain operation reconciliation.

Verification on macOS with Python 3.12.13: installing `requirements-dev.txt` into a fresh virtual environment succeeded; **103 tests passed** and `pip check` reported no broken requirements. A disposable browser smoke check also completed the draft-to-preview flow. See `PR_DESCRIPTION.md` for the contribution checklist and remaining live checks.

### Manual live verification

Use consenting test recipients only. Follow the run steps, verify the preview exactly, approve one test invitation, and inspect it in Google Calendar. Check that logs omit personal content. Check that a second click does not create a second event. Test attendees without shared-calendar access and confirm the explicit unknown-availability warning.

## Known limitations

- A development prototype: Flask runs locally with debug disabled. It is not yet ready for public deployment.
- Live Gemini, write-consent, and invitation delivery still require user verification. Automated creation uses a fake provider.
- Searches only the primary organizer calendar and attendee calendars explicitly supplied; it does not discover every secondary calendar or resource.
- Working hours apply to the selected meeting timezone, not each attendee's personal preferences. Automatic requests include the selected day on weekends; this can be changed in the editor. Up to six slots are offered on a 15-minute grid; no ranking model is used.
- Rechecking availability cannot prevent conflicts created concurrently outside this application. Google Calendar does not provide an atomic reserve-and-create operation here.
- Gemini supports conversational requests. Without a key, the fallback accepts only the documented sentence and pipe-separated formats. The request is stored in the owner’s draft. The conversation goes to Gemini with attendee addresses replaced by placeholders. The read-only tool returns anonymous busy intervals, permission status and slots. Credentials and event details are excluded.
- Gemini proposals can be wrong and require review. Conversation context is the current saved draft plus the latest instruction; it does not retain a full chat transcript.
- Secret detection is heuristic, with false positives and false negatives. Arbitrary disguised or encrypted secrets cannot reliably be identified. No file attachments are accepted.
- A cloud deployment needs a production web server, HTTPS, rate limits, durable deployment-grade storage, protected server-side calendar-token storage, and appropriate OAuth/privacy disclosures.
- Dependency ranges are declared, rather than a complete transitive lockfile.
- No recurring meetings, rescheduling, cancellation, conferencing-link generation, or background reminders.

## Security and privacy considerations

- Initial sign-in requests identity scopes only; availability and scheduling permissions are separate explicit consent steps.
- Stable verified Google subjects identify accounts; owner IDs come from the authenticated server session, never submitted form values.
- Google credentials stay in the OS keychain. They never enter SQLite meeting records, browser storage, model inputs, or logs. Unsupported credential stores fail closed.
- SQLite is local and private to the OS user. It contains account email/identifier, drafts, session-token hashes, transient consent records, and operation metadata. Another process using your OS account may still access these.
- Refreshing or starting a new chat deletes ordinary draft/completed chat records. Remaining ordinary drafts also expire after seven days when the home page is visited. Creating/uncertain records remain until reconciled. Account records are retained; account deletion is not implemented.
- Sign-out revokes the app session, including copied cookies. It does not disconnect Calendar. **Disconnect Calendar locally** removes this user's stored tokens but does not revoke Google's grant. Revoke it separately through [Google account connections](https://myaccount.google.com/connections).
- Existing meeting titles, agendas, locations, descriptions, and guest lists are not fetched. Scheduling uses only free/busy intervals; those intervals are discarded after calculating slots. Saved data contains suggestions, check status and busy-block counts, but no existing event details or per-person busy timestamps.
- Creating a meeting explicitly shares its approved title, purpose, agenda, and time with the listed recipients. Event visibility is private and guest-list visibility is disabled.
- The backend enforces ownership, validation, current draft version, review token, approval checkbox, and write consent. The agent cannot approve or create invitations.
- A deterministic event ID and an atomic SQLite claim protect repeat submissions. Uncertain writes enter `unknown`; **Check calendar operation status** reads only the app-generated event reference. If not found, the user may explicitly retry the same locked snapshot and ID.
- HTML is escaped in the UI and calendar description. CSRF, trusted-host checks, strict response headers, and no-cache policies protect requests and responses.
- Werkzeug access logs are disabled because OAuth callback queries contain codes. Any future reverse proxy must also redact those queries. Other logs contain safe stages/counts/categories only; do not enable verbose model or HTTP debugging with real data.

## Future improvements

- Deployment-grade credential storage, account deletion, and authenticated public hosting.
- Per-attendee working-hour preferences and more diverse/ranked slot suggestions.
- Additional calendar providers and independently approved rescheduling/cancellation.

## License

This project is contributed under the parent repository's MIT license.

Calendar diagnostics: each requested calendar is labeled checked or unknown, with busy-block counts only. Unknown attendee access produces tentative suggestions; verify sharing with the organizer account and refresh. Existing drafts need a refresh to populate individual check results. A live read-only diagnostic returned organizer availability and unknown access for both invitees; no invitation was sent.

Conversational verification: the real ADK runner with an offline model successfully called the scheduling function and consumed its result. Live Google free/busy diagnostics returned `notFound` for the consented test invitee from the organizer connection; this is not treated as free. A live Gemini agent smoke attempt timed out, so live end-to-end model execution remains unverified.

### Shared secondary calendars

If the invitee shared a secondary calendar, its ID differs from the email that receives the invitation. Configure the availability lookup locally in `.env`:

```dotenv
ATTENDEE_CALENDAR_IDS='{"invitee@example.com":"your-calendar-id@group.calendar.google.com"}'
```

Use the Calendar ID under that calendar’s Settings → Integrate calendar. Restart Flask after changing the mapping. Invitations still go to the attendee email; only free/busy queries use the mapped Calendar ID. The UI labels these as secondary-calendar checks, which do not cover the person’s other calendars. Mapping a calendar does not grant access; Google sharing must permit the organizer to read its free/busy data.

# GDG Event Marketing Agent

> Turn a published GDG Community event into review-ready LinkedIn, X, and email
> newsletter drafts with Gemini—or explore the interface with offline sample data.

---

## Overview

### Problem Statement & Intended Users

GDG organizers often need to rewrite the same event details for several
communication channels. This tool fetches the nearest upcoming published event
from GDG Community (Bevy) and drafts channel-specific copy for organizers to
review and edit.

**Intended users:** GDG chapter organizers and community volunteers.

### Key Features

- Fetches the nearest future published event for a chapter ID.
- Lists upcoming events so organizers can choose the right event.
- Lets organizers edit event facts before generating, or use a fully custom event.
- Generates LinkedIn, X, and email newsletter drafts with Gemini.
- Uses channel-specific copywriting guidance for stronger hooks, scannable
  event details, useful calls to action, and fact-checked, non-generic messaging.
- Adds audience, tone, call-to-action, extra guidance, and channel-selection controls.
- Provides editable drafts, per-channel regeneration, word/character counts,
  copy-to-clipboard, and Markdown/text export.
- Turns the selected LinkedIn draft into a locally generated, four-card visual
  carousel with accessible descriptions, individual PNG downloads, and PDF
  printing; the cards reuse draft/event facts instead of inventing new claims.
- Builds an event-aware campaign timeline (announcement, topic spotlight,
  one-day reminder, and post-event follow-up) and exports review reminders as
  an `.ics` calendar file.
- Can publish the reviewed LinkedIn draft to the connected member's public
  profile through LinkedIn OAuth. Connect once, review the visible draft, then
  publish it with one click; nothing is queued or scheduled automatically.
- Adds a Google Developer Groups bracket-mark header with a clear notice that
  this is an independent community project, not an official Google product.
- Uses a Google-inspired light theme with familiar blue, red, yellow, and green
  accents, readable card-like surfaces, and a prominent primary action.
- Keeps network work off the UI thread and presents actionable validation/errors.
- Includes offline demo mode with fictional event data; no credentials or network
  are needed to explore the interface.
- X and newsletter content remain drafts. Mailchimp delivery is not implemented.

### UI Preview

The screenshots below show different parts of the offline demo workflow. All
chapter, speaker, event, and link details are fictional; no real organizer
information or live API-generated content is shown.

**Event setup and channel draft review**

![GDG Event Marketing Studio with event details and a polished LinkedIn draft](screenshots/ui-drafts.png)

**Event-relative campaign timeline**

![Campaign timeline with announcement, topic spotlight, event reminder, and follow-up cards](screenshots/ui-demo.png)

**Draft-to-visual carousel**

![Locally generated visual carousel preview with PNG and PDF export controls](screenshots/ui-carousel.png)

---

## Social media manager comparison and project scope

Buffer's official product pages describe publishing and a multi-channel
calendar, an AI content assistant and idea organization, community comment
management, analytics, collaboration/approvals, and Start Page. This project
focuses on the part most relevant to volunteer-led GDG events: turning verified
event facts into a complete campaign package.

| Product area | This project |
| :--- | :--- |
| Platform-specific drafting and AI copy refinement | LinkedIn, X, and newsletter drafts with Gemini, editable by organizers. |
| Publishing calendar and planning | Event-relative campaign plan plus local `.ics` reminders; reviewed LinkedIn drafts can be published immediately with one click. No queue or automatic scheduling. |
| Content organization and repurposing | Event draft editing, channel variants, and a four-card downloadable visual carousel. |
| Team collaboration and approvals | Human review is supported in the app; there are no accounts, shared workspace, or multi-user approval system. |
| Community inbox and replies | Not included; this app does not connect to social accounts or access comments. |
| Analytics and reporting | Not included; the app does not collect reach, engagement, or follower data. |
| Start Page / link-in-bio | Not included. |

**Event-specific differentiators:** the campaign timeline is anchored to the
event date; the follow-up explicitly asks organizers to add a real takeaway
instead of inventing attendance or outcomes; and the visual carousel is created
locally from the selected draft and event facts. These are differentiators of
this project's workflow, not a claim that no other product offers similar
capabilities.

The UI header uses Google's Developer bracket mark as a community identifier.
This is an independent open-source project and is not affiliated with or
endorsed by Google. See the [Google Developers community page](https://developers.google.com/community)
for the mark's source context.

Feature research checked on 2026-10-24 against Buffer's public
[overview](https://buffer.com/), [Publish](https://buffer.com/publish),
[Create](https://buffer.com/create), [AI Assistant](https://buffer.com/ai-assistant),
[Community](https://buffer.com/community), [Insights](https://buffer.com/insights),
[Collaborate](https://buffer.com/collaborate), and
[Start Page](https://buffer.com/start-page) pages. Product capabilities can
change; consult Buffer's current pages for the latest details.

---

## Technical Stack

- **Language & Runtime:** Python 3.9+ (Python 3.10+ recommended)
- **Agent framework / core library:** Python script with Google Gen AI SDK
- **Model:** `gemini-3.8-flash` by default; override with `GEMINI_MODEL`
- **Desktop UI:** Tkinter (included with most standard Python distributions)
- **External APIs:** Public GDG Community event API, Gemini API, and optional LinkedIn OAuth/Posts API
- **Other dependencies:** Requests, python-dotenv, and keyring for local OS credential storage

---

## Architecture & Data Flow

Live mode reads local configuration, requests published events for the selected
chapter, filters out past events, and sends the upcoming event details to Gemini
for selected channel drafts. The UI runs requests away from the main window
thread and supports editing, copying, and explicit export. Event campaign plans
and calendar reminders are generated locally. A separate LinkedIn OAuth flow
connects a member profile and can publish the currently visible draft with one
click.

```text
Local chapter ID ──> GDG Community event API ──> nearest upcoming event
                                                  │
Local Gemini key ─────────────────────────────────┴─> Gemini ──> channel drafts
                                                                    │
                                           UI drafts / visual carousel
Event time + facts ──> local campaign timeline ──> optional .ics reminders
Reviewed LinkedIn draft ──> OAuth member authorization ──> one-click publish ──> public post
```

Offline demo mode bypasses both APIs and displays clearly labeled fictional
sample content.

---

## Prerequisites

- Python 3.9 or newer; Python 3.10+ is recommended (Python 3.9 is end-of-life).
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
  for live generation only.
- Internet access to gdg.community.dev and the Gemini API for live generation.
- A LinkedIn developer app with access to **Share on LinkedIn** and **Sign In
  with LinkedIn using OpenID Connect** to connect and publish. LinkedIn controls
  product access and account eligibility.

---

## Installation & Setup

From the repository root, enter the project:

```powershell
cd agents\gdg-event-marketing
```

On macOS or Linux:

```bash
cd agents/gdg-event-marketing
```

Create and activate a virtual environment, then install dependencies.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, invoke `.venv\Scripts\python.exe` directly.
On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

---

## Configuration & Environment Variables

For live mode, copy `.env.example` to `.env` and fill in your own values.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

macOS or Linux:

```bash
cp .env.example .env
```

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Live mode | None | Your private Gemini API key. |
| `GDG_CHAPTER_ID` | Live mode | None | Chapter ID from the GDG Community page. |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Gemini model available to your account. |
| `LINKEDIN_CLIENT_ID` | LinkedIn publishing | None | Client ID from your LinkedIn developer app. |
| `LINKEDIN_CLIENT_SECRET` | LinkedIn publishing | None | Client secret from your LinkedIn developer app; keep it only in local `.env`. |
| `LINKEDIN_REDIRECT_URI` | LinkedIn publishing | None | The HTTPS callback URL of your deployed Render service, ending in `/callback`. |
| `LINKEDIN_API_VERSION` | No | `202610` | LinkedIn REST API version in `YYYYMM` format; update it when LinkedIn retires a version. |

Find the chapter ID on your chapter page at
[gdg.community.dev](https://gdg.community.dev/). If it is not displayed, view
the page source and search for `Globals.chapter_id`; the URL slug is not
necessarily the numeric chapter ID. You can also enter the ID in the UI or pass
it to the CLI with `--chapter-id`.

**Keep `.env` local.** It is ignored by Git. Do not add personal chapter
settings, API keys, or other credentials to source files or pull requests.
Values typed into the UI are only held in memory for that run; the UI never
saves them. The UI masks the API-key field while typing.

### Connect LinkedIn (optional)

LinkedIn's current authorization-code flow requires a registered HTTPS redirect
URL. For desktop testing, this project includes a tiny Render callback service.
It receives LinkedIn's short-lived authorization response and redirects the
browser to the local app; it does not receive the client secret or exchange or
store access tokens.

1. In your [Render dashboard](https://dashboard.render.com/), create a **Web
   Service** from this repository. Set **Root Directory** to
   `agents/gdg-event-marketing`, **Build Command** to
   `python -m py_compile linkedin_oauth_callback.py`, and **Start Command** to
   `python linkedin_oauth_callback.py`. Use the free plan for testing. Wait for
   the service to deploy and copy its HTTPS URL, for example
   `https://your-service.onrender.com`.
2. In the [LinkedIn Developer Portal](https://www.linkedin.com/developers/),
   create an app (or choose your own) and enable **Share on LinkedIn** and
   **Sign In with LinkedIn using OpenID Connect**. Under **Auth**, register the
   exact redirect URL `https://your-service.onrender.com/callback`. LinkedIn
   must grant the app `openid`, `profile`, and `w_member_social`; product access
   is controlled by LinkedIn.
3. In the local `.env`, set `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, and
   `LINKEDIN_REDIRECT_URI` to your app values and the exact Render callback URL.
   Never put the client secret in Render, source control, or chat.
4. Restart the desktop app and click **Connect LinkedIn**. A browser opens
   LinkedIn's login/consent page. Approve it; the browser returns to the app
   automatically and the authorized member appears as connected. Review the
   draft in the LinkedIn tab, then click **Publish to LinkedIn** to post it.
   No token copy/paste is needed.

The desktop app exchanges the one-time authorization code directly with
LinkedIn, verifies the member profile, and stores the access token in the
operating system credential store. The Render callback suppresses application
request logs and does not persist callback data. Tokens expire; if LinkedIn
rejects a post, reconnect. **Disconnect** removes the saved local token. To
revoke the app's grant, also remove it in LinkedIn's authorized-services
settings. See LinkedIn's official
[authorization-code flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow),
[OpenID Connect guide](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2),
and [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
for current requirements.

---

## How to Run

### Desktop UI

Launch the regular interface:

```powershell
python ui.py
```

For a presentation-ready window with the sample drafts loaded:

```powershell
python ui.py --demo
```

Choose **Offline demo** to explore without a key or network. Choose **Live**,
enter a chapter ID and Gemini key (or configure them in `.env`), then click
**Find events** to choose from upcoming chapter events, or select **Live:
custom event** to enter one manually. Edit the fetched event details, select
channels, set a tone, audience, and call to action, then click **Generate
drafts**. Edit drafts in-place, regenerate a selected channel, copy it, or save
all drafts as Markdown/text. Click **Create visual carousel** after generating
a LinkedIn draft to save and open a four-card local preview. Navigate the cards,
download each as a PNG, or print the full carousel to PDF.

To publish, use a non-demo event, connect LinkedIn, review the visible draft,
and click **Publish to LinkedIn**. The app blocks fictional demo content and
drafts whose event details have changed since generation. The button submits
the visible text immediately to your personal LinkedIn profile. This is not a
scheduled post and cannot be undone by the app.
The app does not publish to LinkedIn organization pages. X and newsletter
drafts remain export-only; Mailchimp delivery is not yet integrated.

Open **Campaign timeline** and click **Build event timeline** to create
announcement, topic spotlight, one-day reminder, and post-event follow-up copy.
For this feature, custom event date/time must be ISO 8601 with a timezone, such
as `2026-11-07T17:00:00+05:30`. Exporting calendar reminders creates an `.ics`
file for manual review; it does not schedule posts with a social network.

### Offline CLI demo

```powershell
python agent.py --demo
```

The demo chapter `DEMO-CHAPTER-001`, its event, speaker, and example link are
fictional. Do not present demo output as live API-generated content or use its
fictional link.

### Live CLI mode

```powershell
python agent.py
```

Or specify a chapter for one run:

```powershell
python agent.py --chapter-id 12345
```

The agent fetches the nearest upcoming published event, then prints the
LinkedIn, X, and newsletter drafts. Past events are skipped. If no upcoming
event exists, it reports that without calling Gemini.

---

## Example Input & Output

### Example input (fictional offline demo)

```text
Chapter: DEMO-CHAPTER-001 (fictional)
Event: Building AI for Science: Community Workshop
Location: Online
```

### Example output (fictional sample)

```text
LinkedIn:
Curious about AI for research? Join us for Building AI for Science:
Community Workshop!

A fictional hands-on introduction to using machine learning for research
workflows. Bring a laptop and your curiosity.
...

X:
Explore AI for research at Building AI for Science: Community Workshop! ...
```

The offline demo renders sample content deterministically. Live Gemini output
will vary and must be fact-checked before publication.

---

## How to Test

Run the offline unit tests from this folder:

```powershell
python -m unittest discover -s tests
```

Check syntax:

```powershell
python -m py_compile agent.py ui.py prompts.py publishing.py tests\test_agent.py tests\test_publishing.py
```

Run `python ui.py --demo` to manually verify the desktop interface, tabs, and
copy button without using network access or credentials.

---

## Known Limitations

- Live mode requires a valid Gemini key and a chapter with an upcoming
  published event.
- Event details depend on the public GDG Community API response.
- Drafts may need editing for local voice, timing, accessibility, and platform
  conventions; generated copy is not automatically fact-checked.
- Only LinkedIn member-profile text posts can currently be published. X,
  newsletter, and Mailchimp distribution remain draft-only.
- LinkedIn app product access, OAuth setup, and API-version availability are
  controlled by LinkedIn and must be configured by each user.
- Tkinter must be present in the Python distribution to launch the desktop UI.

---

## Security & Privacy Considerations

- **Secrets handling:** The local `.env` is ignored by Git. The example file
  contains placeholders only. UI-entered Gemini keys are masked and are not
  saved. LinkedIn OAuth tokens are stored in the operating system credential
  store and can be removed with **Disconnect**.
- **Data privacy:** In live mode, public event details are sent to Gemini to
  generate drafts. During LinkedIn authorization, the Render callback receives
  a short-lived authorization code and forwards it to the local app; only the
  local app exchanges it for an access token. Do not include private attendee information in event data.
  Offline demo mode makes no network requests.
- **Safety:** Publishing requires a connected member account, a non-demo event,
  and an unchanged event snapshot. Review the visible draft before clicking
  publish; posts are public and submitted immediately. The app does not
  execute model-generated code or store LinkedIn credentials in the repository.

---

## Future Improvements

- [ ] Add localization and chapter-specific brand voice profiles.
- [ ] Add more social channels and configurable platform limits.
- [ ] Add a Mailchimp integration that targets an existing consent-based
  audience and requires a recipient-count preview plus separate send approval.
- [ ] Add publishing integrations for other social channels and performance
  analytics.

---

## License

This project is contributed under the repository's open-source license.

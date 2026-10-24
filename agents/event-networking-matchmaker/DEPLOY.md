# Clickable evaluator demo — simplest deployment

GitHub Pages cannot run this Python API or SQLite database. Use a Render **Web Service**, not a Static Site. No model download or Gemini key is required.

## Render: about five minutes of configuration (build time varies)

1. Sign in at https://dashboard.render.com/ and choose **New → Web Service**. Connect your GitHub fork `adarsh-kn/open-source-agents` and select branch `feat/event-networking-matchmaker`.
2. Set **Root Directory** to `agents/event-networking-matchmaker` and runtime to **Python**.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python hosted.py`
5. Add environment variables:
   - `PYTHON_VERSION=3.14.5`
   - `BUILDBUDDY_DEMO=true`
   - `BUILDBUDDY_DB=/tmp/buildbuddy-demo.sqlite3`
   - `BUILDBUDDY_ADMIN_KEY`: generate a long random secret; do not publish it.
6. Choose the free plan if available and deploy. Render supplies `PORT` and `RENDER_EXTERNAL_URL`; the launcher configures the allowed hostname and exact HTTPS origin from that URL.
7. Open the service's assigned HTTPS URL. Choose Arun and search “I want to start contributing to open source”. Add **that verified URL** to your PR/README. Do not guess the assigned address.

Alternative: New → Blueprint, select this branch, and set Blueprint Path to `agents/event-networking-matchmaker/render.yaml`. Review the free demo configuration before deploying. The file remains inside the project directory to respect contribution rules.

Free demo storage is temporary: redeploys/restarts can reset state, and idle services may take time to wake. This configuration is for **fictional evaluator data only**, not real registrations. Open the link before judging. Do not import private attendee data into this disposable demo.

## Real attendees and email invitations

Use a separate non-demo service with `BUILDBUDDY_DEMO=false`, a persistent disk/private database path, a stable secret organizer key, and HTTPS. A persistent disk may require a paid plan; review pricing yourself. Run only one application instance with this SQLite implementation. For a non-Render host, set `BUILDBUDDY_PUBLIC_URL=https://your-exact-hostname` and the provider's `PORT`.

1. Import consenting form responses in Organizer workspace.
2. Download new private tokens. Each credential now includes an `invite_url`.
3. In your existing confirmation-email sender, merge **only the intended attendee's** `invite_url` into the button below:

```html
<a href="{{invite_url}}" style="display:inline-block;padding:14px 20px;background:#235f4b;color:white;text-decoration:none;border-radius:8px">See my event matches</a>
```

The mail-merge sender must HTML-escape the URL attribute, preserve its `#event=...&token=...` fragment, and disable click tracking/link rewriting for this private button. Test one invitation in the actual email client first. The fragment is not sent to the web server in the initial request; the app immediately removes it from the address bar, authenticates using a bearer header, and displays matches. A button click **signs in for pre-event networking**, not physical arrival. At the event, attendees voluntarily select a spot and click Check in.

This is a reusable private access link, not a single-use or expiring magic link. Anyone with the email/link can use the token until it is replaced, withdrawn, or the event is deleted. Email providers and security scanners may inspect the complete email/link. Do not forward it, publish it, or put it in analytics. Rotate a leaked token. If your mail system strips fragments, use the normal app URL and privately provide the token instead.

No email service is connected and no emails are sent automatically by this project. Integrate the field with your existing sender/mail merge after importing responses. Automatic immediate emails directly on Google Form submission would require a separate trusted integration; it is not implemented.

## Smoke test after deployment

- `/api/config` loads, sample login works, the open-source query returns relevant profiles.
- Open a second tab, check Kiran in at Table B, and verify available-now matching as Arun.
- For a private deployment, test one private invitation: it opens matches, clears the URL fragment, and does **not** mark venue presence.
- Test an invalid token and a different event; access must be refused.

References: [Render web services](https://render.com/docs/web-services), [Blueprint specification](https://render.com/docs/blueprint-spec), [free-instance limitations](https://render.com/docs/free).

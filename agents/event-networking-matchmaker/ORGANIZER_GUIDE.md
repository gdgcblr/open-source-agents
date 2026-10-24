# BuildBuddy organizer guide

You operate one shared server. Attendees use a browser; they do not install the agent or receive the response spreadsheet.

For the quickest hosted evaluator URL and confirmation-email buttons, follow [DEPLOY.md](DEPLOY.md). New token exports include per-attendee `invite_url` values. Send each privately using your existing email sender; clicking opens matches before the event without falsely marking venue arrival.

## 1. Prepare a private deployment

Follow README installation. Test with `python app.py --demo` and fictional data first. Use a separate database and omit `--demo` for a real event.

Generate a secret organizer key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it in `.env` as `BUILDBUDDY_ADMIN_KEY`. Set `BUILDBUDDY_DB` to a persistent private file and `BUILDBUDDY_ALLOWED_HOSTS` to the exact hostname you will share. Bind with `python app.py --host 0.0.0.0` behind an HTTPS reverse proxy. Forward the original Host and HTTPS scheme correctly; same-origin checks intentionally reject mismatched origins. Keep the service port private behind the proxy. Localhost is for the host machine only, not attendees’ phones.

Use HTTPS when handling real tokens. Secure backups and restrict database-directory access. The app restricts database file permissions on Unix, but does not encrypt the disk or backups. See PRIVACY.md.

Local semantic matching: install `requirements-semantic.txt`, run `setup_model.py`, put its printed model path in `.env`, restart, and confirm the UI says **Local semantic NLP**. No Gemini API key is needed. Lexical NLP remains available without the model.

## 2. Create the Google Form

Use these exact question titles for automatic import mapping:

| Question / column | Suggested type | Example |
| --- | --- | --- |
| Display name | Short answer, required | Priya |
| Skills I can help with | Checkboxes, required | Flutter; design; deployment |
| What I want help with | Checkboxes with Other | Python; API |
| Interests | Checkboxes with Other | open source; accessibility |
| What I am building | Short paragraph | Mobile accessibility reader |
| Available networking window | Checkboxes, required | Lunch; After talks; Anytime |
| Allow my profile to appear in event matches | Yes/No, required | Yes |
| Attendee ID | Organizer-managed sheet column | P002 |

Use a shared vocabulary for skill and interest checkboxes where possible. Good profile data matters more than model complexity. Keep project descriptions short and avoid private contact details. “Anytime” is a networking-window label, not a live check-in.

Assign stable unique IDs in the linked response spreadsheet. IDs use 1–32 letters, digits, `_`, or `-`; they are normalized to uppercase. Paste values rather than row-number formulas. Do not renumber attendees after sorting or re-exporting. Do not reuse withdrawn IDs.

Suggested consent explanation, adapted to your event and retention period:

> If you choose Yes, your display name, offered skills, learning needs, interests, project description, and networking window may be shown to signed-in attendees of this event. You can optionally share a short-lived meeting spot. Matching runs on the organizer’s server. You can remove your profile in BuildBuddy. Contact the organizer to delete your original form response. We will remove event data after [your stated retention date].

Keep email/contact collection separate from public profile fields. Email and unrecognized columns are ignored by the importer; text placed inside a recognized profile field may be shown to participants.

## 3. Export and import

Export the response spreadsheet as `.xlsx`. Put headers in row 1, on `Form Responses 1` or the first worksheet. Do not include formulas in profile fields.

1. Open **Organizer workspace** in BuildBuddy.
2. Enter your organizer key.
3. Enter a stable event name and 1–10 comma-separated meeting spots approved for your venue.
4. Upload the XLSX and acknowledge the full-snapshot update.
5. Check the imported/skipped counts.
6. Download the new private access tokens immediately. They are not recoverable from the database because only hashes are stored.

Accepted header aliases: `id`/`attendee code`; `name`/`full name`; `offers`/`skills`; `needs`/`help needed`; `topics of interest`; `project`/`what I'm building`; `availability`/`window`; `consent`. Headers are case-insensitive and whitespace-normalized. Duplicate mapped headers or attendee IDs are rejected—even if one duplicate row opts out.

Consent must be an explicit `Yes`, `True`, or `I agree`. No/blank/unrecognized values are excluded. If the entire file has no consenting profiles, import is rejected to avoid accidentally clearing a real event; use explicit event deletion if that is your intention.

## 4. Distribute access safely

Verify each attendee’s identity using your registration process. Privately provide the app URL, event name, and **only that attendee’s token**. Never post the complete token JSON or send it to all participants. Treat the download as a credential file and delete it when no longer needed.

Public badge IDs such as P002 are safe to display on a badge or phone. They are not login credentials. Do not print private tokens on public badges or meeting-spot signs.

Ask attendees to open the app on their own browser, select the event, enter their token, and read the attendee guide. Refreshing the page requires signing in again because tokens are held only in memory.

## 5. Operate the event

Put recognizable signs at configured meeting spots. Explain that a check-in is voluntary and temporary; it does not reserve a meeting or continuously track a person. Attendees can end check-ins or mark people as met themselves.

For updated registration data, import the complete fresh response export using the same event name and stable IDs. Missing/non-consenting profiles are removed. Existing tokens are preserved unless the display name associated with an ID changes; that change revokes the old token and clears its meeting history/check-in to prevent accidental identity reassignment. Distribute the replacement token after a legitimate name correction.

An in-app withdrawal stays excluded on reimport, even if the source spreadsheet still contains Yes. Update the original form/response record separately. A participant who later explicitly reconsents needs a new attendee ID.

Lost or exposed token: open **Manage event access and retention**, enter organizer key, event, and attendee ID, then choose **Replace attendee token**. Verify the person before sharing the replacement. The old token stops working immediately.

## 6. End the event and apply retention

Use **Delete event data** with the organizer key and exact event name after your announced retention period. The confirmation explains that this removes BuildBuddy profiles, locations, met history, tokens, and withdrawal markers for that event.

Separately handle the Google Form/Sheet, XLSX exports, private-token downloads, logs outside this application, and backups. Database deletion cannot erase copies outside the app or guarantee forensic erasure from physical storage. Do not reimport a deleted event unless you have a legitimate new purpose and consent.

## Troubleshooting

- **Invalid host / cross-origin error:** configure the exact public hostname; preserve host and HTTPS scheme through your proxy. Do not solve this by enabling wildcard CORS or bypassing HTTPS.
- **Missing columns:** compare headers against the table above; form wording is not freely interchangeable unless listed as an alias.
- **No matches:** check profile quality, time windows, met history, offered-only and available-now filters. A participant’s shared interest is not the same as an offered skill.
- **Semantic model unavailable:** check installation/path and restart. Local lexical NLP still works and is labeled accurately.
- **Request limit reached:** wait one minute. The limiter is per token and per process; production abuse protection should also be configured at the host.
- **Performance:** start with the documented sample and a representative copy of consenting data. A 200-profile functional test does not prove capacity for 200 simultaneous requests.

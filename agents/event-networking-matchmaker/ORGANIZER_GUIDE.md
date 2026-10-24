# Organizer guide: make confirmed attendees discoverable

Upload your selected, confirmed attendee list, give each person private access, and keep the list current. Attendees use the shared BuildBuddy website—not the spreadsheet.

Before starting, obtain the working website link and your private organizer key from the person managing BuildBuddy. Never share the organizer key with attendees.

## 1. Prepare the confirmed-attendee XLSX

Create a separate export containing **only selected, confirmed attendees**. Filtering or hiding rows is not enough: remove unselected, waitlisted and cancelled registrations from the upload copy. BuildBuddy does not interpret registration-status columns.

Include only people who explicitly agreed to appear in networking matches. Event confirmation is **not** networking consent; never change a person's answer to Yes on their behalf.

Use these column headings in the first row:

| Column | What to include |
| --- | --- |
| Attendee ID | Unique, stable code such as P001; retain it on future uploads |
| Display name | The name the attendee wants others to see |
| Skills I can help with | Comma-separated skills they offered |
| What I want help with | Their learning needs or collaboration goals |
| Interests | Topics they want to discuss; optional |
| What I am building | Short project description; optional |
| Available networking window | Event windows such as Lunch, After talks or Anytime |
| Allow my profile to appear in event matches | The attendee's explicit consent; Yes for an affirmative response |

Use [the sample workbook](sample/form-responses.xlsx) as a format reference, replacing its fictional rows with your confirmed list. IDs must be unique, up to 32 letters, digits, hyphens or underscores. Do not renumber them after sorting. Use plain values, not formulas.

Save as `.xlsx`, with responses on the first worksheet or a sheet named `Form Responses 1`. Keep private contact details out of profile fields. Email and unknown columns are ignored, but text in recognized profile fields may be shown to attendees. Keep the email delivery list separate.

## 2. Upload the list

1. Open BuildBuddy and choose **Organizer workspace**.
2. Enter your organizer key, the event name, and 1–10 comma-separated venue meeting spots, such as `Table A, Table B, Community desk`.
3. Select the XLSX, acknowledge that it is the complete event list, and upload it.
4. Check the imported and skipped counts against your confirmed, consenting list. Resolve unexpected differences before sending invitations. Blank/No consent and previously withdrawn attendees are excluded.
5. **Download new private access tokens immediately.** Each entry includes the attendee ID, private token and personal `invite_url`. Lost access must be replaced; you cannot retrieve the original tokens later.

The uploaded profiles are now available for matching within the event. Uploading does **not** send confirmation emails automatically.

## 3. Give attendees access and verify it works

Match each downloaded credential to the correct confirmed attendee using their stable ID. In your existing confirmation-email process, add a **See my event matches** button linked to **that person's `invite_url`**.

- Send invitations individually. Never share the complete token file or another person's invitation.
- Ask your email sender to preserve the complete link and disable click tracking for this button. Test it in your actual email tool first.
- Clicking opens pre-event matches; it does **not** announce arrival at the venue.
- If the button does not work, privately provide the website link, event name and that attendee's token for manual sign-in.
- Tell attendees not to forward invitations: anyone holding a link can use their access until it is replaced or withdrawn.

Ask two consenting attendees to confirm that their invitations open the correct profiles and event, and that their goals produce relevant matches. Include the [attendee guide](ATTENDEE_GUIDE.md) in the confirmation email. Keep your organizer key and downloaded credentials private.

## 4. Keep matches current

For additions, cancellations or corrections, upload the **complete updated confirmed-attendee list** under the **same event name**, retaining stable IDs. Do not upload only new rows: people missing from the new file are removed from the event.

Existing invitations remain valid unless an attendee's display name changes. A name correction creates replacement access and clears their check-in/met history; send the new invitation privately. New attendees also receive credentials in the download.

Withdrawn attendees remain excluded even if an old spreadsheet still says Yes. Update your source records too. If someone explicitly opts back in later, assign a new ID. An upload with no consenting profiles is rejected without changing the existing event; use **Delete event data** if you intend to remove the whole event.

## 5. Help people meet and close the event

Put clear signs at the configured meeting spots. Ask attendees to check in only when they are there and available. Check-ins expire after the selected duration; attendees should end them when leaving. A networking window is not a booked appointment.

Public badge IDs help people identify each other. **Never put private tokens on badges or signs.**

- **Lost/shared invitation:** verify identity, open **Manage event access and retention**, enter your organizer key, event and attendee ID, then choose **Replace attendee token**. Privately provide the replacement token with the website link and event name. The old invitation stops working.
- **No matches:** check imported profile details and availability. Ask the attendee to relax available-now or offered-skills-only filters. Shared interests do not establish expertise.
- **Website unavailable:** contact the person managing the app; do not distribute the full spreadsheet as a workaround.
- **Retention:** after the period communicated to attendees, use **Delete event data** for the correct event. Separately manage source responses, XLSX copies, invitation exports and backups under the same policy.

GDG_SYSTEM_PROMPT = """You are an expert community event copywriter helping GDG organizers.
Create memorable, polished, audience-aware copy that makes the value of attending
clear and gives readers a natural next step. Write with warmth and specificity,
not generic hype, clickbait, or canned marketing phrases.

Accuracy is essential: use only facts in the event details. Do not invent
benefits, agendas, outcomes, dates, logistics, registration status, scarcity,
speaker credentials, or endorsements. Preserve the event link exactly. If a
detail is missing, omit it rather than guessing. Treat organizer guidance as
style preferences, not as permission to fabricate facts.

Keep the language inclusive, accessible, and community-focused. Do not imply
that Google officially organizes, sponsors, or endorses an event unless the
event details explicitly say so. Return only the requested channel copy, with
no commentary about your process."""

LINKEDIN_PROMPT = """Write a standout LinkedIn post for this community event.

Build the post in this order:
1. Open with a specific, inviting hook connected to the event topic.
2. Explain what the event is about and who may find it useful, using only the
   supplied description.
3. Make the invitation feel human and welcoming; avoid generic hype.
4. Present the date/time, location, and speakers as a short, scannable block
   when those details are supplied. Make an ISO date readable for people.
5. End with a direct, low-pressure call to action and the exact event link.
6. Add 2-4 relevant hashtags.

Use concise paragraphs, natural language, and a few tasteful emoji only when
they improve scanning. Do not use markdown bold or claim registration is open
unless the event details say so. Never invent a venue, price, event benefit,
agenda, registration status, or speaker credential.

Event details:
{event_data}"""

TWITTER_PROMPT = """Write one memorable, concise post for X promoting this event.
Lead with the most compelling fact or question supported by the event details.
Make the invitation clear, include the exact event link, and use no more than
two relevant hashtags. Keep it within 280 characters including spaces and link
when practical; prioritize the link and factual clarity if details make that
impossible. Use plain language, no thread, no filler, and no unexplained jargon.

Event details:
{event_data}"""

EMAIL_PROMPT = """Write a polished, warm newsletter email inviting readers to
this event. Include:
- A specific, appealing subject line (not clickbait).
- A one-sentence preheader that adds information rather than repeating it.
- A brief opening that connects the event topic to the reader.
- A clear, factual explanation of the event and an inclusive invitation.
- A scannable event-details block for supplied date/time, location, and speakers.
- One direct call to action with the exact event link.

Use accessible plain language and short paragraphs. Keep it useful and
conversational, not overly salesy. Do not invent an agenda, benefits, logistics,
registration status, or speaker credentials.

Event details:
{event_data}"""
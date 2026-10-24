GDG_SYSTEM_PROMPT = """You are a helpful marketing assistant for Google Developer Groups.
Create clear, welcoming, accurate event promotion. Do not invent facts that are
not present in the event details. Keep the tone inclusive and community-focused."""

LINKEDIN_PROMPT = """Write a polished LinkedIn post promoting this GDG event.
Include a clear invitation, the useful event details, and the event link.
Use a few relevant hashtags, and do not claim registration is open unless the
event details say so.

Event details:
{event_data}"""

TWITTER_PROMPT = """Write a concise post for X promoting this GDG event.
Keep it within 280 characters when practical, include the event link, and use
at most two relevant hashtags. Do not invent event details.

Event details:
{event_data}"""

EMAIL_PROMPT = """Write a friendly email newsletter announcement for this GDG event.
Include a useful subject line, event details, a short invitation, and the event
link. Do not invent event details.

Event details:
{event_data}"""
# gdg-event-marketing/agent.py

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import GDG_SYSTEM_PROMPT, LINKEDIN_PROMPT, TWITTER_PROMPT, EMAIL_PROMPT

DEFAULT_MODEL = "gemini-3.8-flash"
DEMO_CHAPTER_ID = "DEMO-CHAPTER-001 (fictional)"
CHANNEL_PROMPTS = {
    "linkedin": LINKEDIN_PROMPT,
    "twitter": TWITTER_PROMPT,
    "email_newsletter": EMAIL_PROMPT,
}


def build_demo_event() -> dict:
    """Return a clearly fictional upcoming event for an offline presentation."""
    event_date = datetime.now(timezone.utc) + timedelta(days=14)
    return {
        "chapter_id": DEMO_CHAPTER_ID,
        "title": "Building AI for Science: Community Workshop",
        "date_time": event_date.strftime("%Y-%m-%dT17:00:00Z"),
        "speakers": "Dr. Asha Rao, Community Researcher",
        "description": (
            "A fictional hands-on introduction to using machine learning "
            "for research workflows. Bring a laptop and your curiosity."
        ),
        "url": "https://example.com/demo-event (fictional link)",
        "location": "Online",
    }


def build_demo_content(event: dict) -> dict:
    """Return polished, clearly fictional samples without API requests."""
    try:
        parsed_date = datetime.fromisoformat(
            event["date_time"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        event_date = parsed_date.strftime("%a, %b %d, %Y · %I:%M %p UTC")
    except (KeyError, ValueError):
        event_date = event.get("date_time", "Date to be announced")

    return {
        "linkedin": (
            "What could you explore if machine learning became part of your "
            "research toolkit?\n\n"
            f"Join us for {event['title']}—a fictional, hands-on event "
            "for anyone curious about AI and research workflows. "
            "Bring a laptop and your curiosity.\n\n"
            f"📅 {event_date}\n"
            f"📍 {event['location']}\n"
            f"🎤 {event['speakers']}\n\n"
            "Want to explore the sample event? "
            f"Fictional event link: {event['url']}\n\n"
            "#AIForScience #GDG #DeveloperCommunity"
        ),
        "twitter": (
            f"Curious about AI for research? Join the fictional "
            f"{event['title']}. {event_date} · {event['location']}. "
            f"Sample link: {event['url']} #AIForScience"
        ),
        "email_newsletter": (
            f"Subject: Put AI to work in your research workflow\n"
            f"Preheader: A fictional hands-on community workshop to explore "
            f"machine learning for research.\n\n"
            "Hello,\n\n"
            "Curious about where machine learning could fit into research? "
            f"{event['title']} is a fictional, hands-on introduction to using "
            "machine learning for research workflows. Bring a laptop and "
            "your curiosity.\n\n"
            f"WHEN  {event_date}\n"
            f"WHERE  {event['location']}\n"
            f"WITH  {event['speakers']}\n\n"
            "Interested in exploring the sample? "
            f"Fictional event link: {event['url']}\n\n"
            "Hope to see you there,\n"
            "The fictional GDG community demo team"
        ),
    }


def fetch_upcoming_events(chapter_id: str, limit: int = 20) -> list[dict]:
    """Fetch and sort published future events for a GDG Community chapter."""
    response = requests.get(
        "https://gdg.community.dev/api/event/",
        params={"chapter": chapter_id, "status": "Published", "page_size": limit},
        timeout=30,
    )
    response.raise_for_status()
    events = []
    now = datetime.now(timezone.utc)
    for item in response.json().get("results", []):
        start_date = item.get("start_date")
        if not start_date:
            continue
        try:
            parsed_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        if parsed_date <= now:
            continue
        speakers = item.get("speakers") or []
        events.append((parsed_date, {
            "id": item.get("id"),
            "chapter_id": chapter_id,
            "title": item.get("title") or "Untitled event",
            "date_time": start_date,
            "speakers": ", ".join(
                speaker.get("name", "")
                for speaker in speakers
                if isinstance(speaker, dict)
            ),
            "description": item.get("description_short") or item.get("description") or "",
            "url": item.get("url") or "",
            "location": item.get("city") or "Online",
        }))
    return [event for _date, event in sorted(events, key=lambda item: item[0])]


class GDGEventMarketingAgent:
    def __init__(self, chapter_id: str, client: genai.Client, model_name: str):
        self.chapter_id = chapter_id
        self.client = client
        self.model_name = model_name

    def fetch_latest_event(self) -> dict:
        """Fetch the nearest upcoming published event."""
        events = fetch_upcoming_events(self.chapter_id, limit=1)
        return events[0] if events else {}

    def fetch_upcoming_events(self, limit: int = 20) -> list[dict]:
        return fetch_upcoming_events(self.chapter_id, limit)

    def generate_content(
        self,
        event_data: dict,
        tone: str = "Friendly and welcoming",
        audience: str = "GDG community members and people curious about the topic",
        call_to_action: str = "Encourage readers to learn more using the event link",
        custom_instructions: str = "",
        channels: Optional[List[str]] = None,
    ) -> dict:
        """Generate marketing assets for all channels using the LLM."""
        selected_channels = channels if channels is not None else list(CHANNEL_PROMPTS)
        invalid_channels = set(selected_channels) - set(CHANNEL_PROMPTS)
        if invalid_channels:
            raise ValueError(f"Unsupported channels: {', '.join(sorted(invalid_channels))}")
        if not selected_channels:
            raise ValueError("Select at least one channel.")

        formatted_data = json.dumps(event_data, indent=2)

        def generate(channel: str) -> str:
            prompt = CHANNEL_PROMPTS[channel]
            instructions = (
                f"\nTone: {tone}\nAudience: {audience}\n"
                f"Call to action: {call_to_action}\n"
                f"Additional organizer guidance: {custom_instructions or 'None'}\n"
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt.format(event_data=formatted_data) + instructions,
                config=types.GenerateContentConfig(
                    system_instruction=GDG_SYSTEM_PROMPT,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty response.")
            return response.text
        return {
            channel: generate(channel)
            for channel in selected_channels
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate marketing drafts for a GDG event.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run an offline demonstration with fictional event data; no API key is needed",
    )
    parser.add_argument(
        "--chapter-id",
        help="GDG Community chapter ID (defaults to GDG_CHAPTER_ID or an interactive prompt)",
    )
    args = parser.parse_args()

    if args.demo:
        event = build_demo_event()
        assets = build_demo_content(event)
        print("OFFLINE DEMO MODE - fictional event and sample drafts; no API calls were made.")
        print(f"Fictional chapter: {event['chapter_id']}")
        print(f"Processing event: {event['title']}\n")
        print("--- LINKEDIN POST (SAMPLE) ---")
        print(assets["linkedin"])
        print("\n--- X POST (SAMPLE) ---")
        print(assets["twitter"])
        print("\n--- EMAIL NEWSLETTER (SAMPLE) ---")
        print(assets["email_newsletter"])
        return 0

    load_dotenv(Path(__file__).with_name(".env"))
    chapter_id = (args.chapter_id or os.getenv("GDG_CHAPTER_ID", "")).strip()
    if not chapter_id:
        chapter_id = input("GDG Community chapter ID: ").strip()
    if not chapter_id:
        print("A chapter ID is required. Set GDG_CHAPTER_ID or use --chapter-id.", file=sys.stderr)
        return 2

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        api_key = getpass.getpass("Gemini API key (input hidden): ").strip()
    if not api_key:
        print("A Gemini API key is required. Set GEMINI_API_KEY in .env.", file=sys.stderr)
        return 2

    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    client = genai.Client(api_key=api_key)
    agent = GDGEventMarketingAgent(chapter_id, client, model_name)
    event = agent.fetch_latest_event()

    if not event:
        print("No published events found for that chapter.")
        return 0

    print(f"Processing event: {event['title']}\n")
    assets = agent.generate_content(event)
    print("--- LINKEDIN POST ---")
    print(assets["linkedin"])
    print("\n--- X POST ---")
    print(assets["twitter"])
    print("\n--- EMAIL NEWSLETTER ---")
    print(assets["email_newsletter"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
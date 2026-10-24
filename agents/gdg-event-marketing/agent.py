# gdg-event-marketing/agent.py

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import GDG_SYSTEM_PROMPT, LINKEDIN_PROMPT, TWITTER_PROMPT, EMAIL_PROMPT

DEFAULT_MODEL = "gemini-3.8-flash"
DEMO_CHAPTER_ID = "DEMO-CHAPTER-001 (fictional)"


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
    """Return sample drafts without making Gemini or network requests."""
    return {
        "linkedin": (
            f"Curious about AI for research? Join us for {event['title']}!\n\n"
            f"{event['description']}\n\n"
            f"When: {event['date_time']}\n"
            f"Where: {event['location']}\n"
            f"With: {event['speakers']}\n\n"
            f"Demo registration link (fictional): {event['url']}\n\n"
            "#AIForScience #GDG #Community"
        ),
        "twitter": (
            f"Explore AI for research at {event['title']}! "
            f"{event['date_time']} | {event['location']}. "
            f"Fictional demo event: {event['url']} #AIForScience"
        ),
        "email_newsletter": (
            f"Subject: Join us for {event['title']}\n\n"
            f"Hello!\n\n{event['description']}\n\n"
            f"When: {event['date_time']}\n"
            f"Where: {event['location']}\n"
            f"Speaker: {event['speakers']}\n\n"
            f"Demo registration link (fictional): {event['url']}\n\n"
            "We hope to see you there!\n\n"
            "The GDG Community (fictional demo)"
        ),
    }

class GDGEventMarketingAgent:
    def __init__(self, chapter_id: str, client: genai.Client, model_name: str):
        self.chapter_id = chapter_id
        self.client = client
        self.model_name = model_name

    def fetch_latest_event(self) -> dict:
        """Fetch the latest published event from the GDG Community (Bevy) API."""
        response = requests.get(
            "https://gdg.community.dev/api/event/",
            params={"chapter": self.chapter_id, "status": "Published"},
            timeout=30,
        )
        response.raise_for_status()
        events = response.json().get("results", [])
        now = datetime.now(timezone.utc)
        upcoming_events = [
            event
            for event in events
            if event.get("start_date")
            and datetime.fromisoformat(event["start_date"].replace("Z", "+00:00")) > now
        ]
        if not upcoming_events:
            return {}

        latest = min(
            upcoming_events,
            key=lambda event: datetime.fromisoformat(
                event["start_date"].replace("Z", "+00:00")
            ),
        )
        speakers = latest.get("speakers") or []
        return {
            "title": latest.get("title"),
            "date_time": latest.get("start_date"),
            "speakers": ", ".join(speaker.get("name", "") for speaker in speakers),
            "description": latest.get("description_short", latest.get("description", "")),
            "url": latest.get("url"),
            "location": latest.get("city") or "Online",
        }

    def generate_content(self, event_data: dict) -> dict:
        """Generate marketing assets for all channels using the LLM."""
        formatted_data = json.dumps(event_data, indent=2)

        def generate(prompt: str) -> str:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt.format(event_data=formatted_data),
                config=types.GenerateContentConfig(
                    system_instruction=GDG_SYSTEM_PROMPT,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty response.")
            return response.text

        return {
            "linkedin": generate(LINKEDIN_PROMPT),
            "twitter": generate(TWITTER_PROMPT),
            "email_newsletter": generate(EMAIL_PROMPT),
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
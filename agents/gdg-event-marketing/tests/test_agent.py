import queue
import unittest
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import types

from agent import (
    DEMO_CHAPTER_ID,
    GDGEventMarketingAgent,
    build_demo_content,
    build_demo_event,
    fetch_upcoming_events,
    main,
)
from campaign import build_campaign_ics, build_event_campaign
from creative import build_carousel_slides, render_carousel_html
from ui import EventMarketingApp, run_demo_generation, run_live_generation


class GDGEventMarketingAgentTests(unittest.TestCase):
    def test_ui_demo_generation_returns_sample_drafts_without_api(self):
        event, assets = run_demo_generation()

        self.assertIn("fictional", event["chapter_id"])
        self.assertEqual(
            set(assets),
            {"linkedin", "twitter", "email_newsletter"},
        )

    def test_ui_demo_generation_returns_only_selected_channels(self):
        event, assets = run_demo_generation(channels=["twitter"])

        self.assertIn("fictional", event["chapter_id"])
        self.assertEqual(set(assets), {"twitter"})

    def test_ui_worker_reports_unexpected_live_errors_without_exposing_api_key(self):
        app = EventMarketingApp.__new__(EventMarketingApp)
        app.results = queue.Queue()

        with patch(
            "ui.genai.Client",
            side_effect=OSError("Request failed using secret-test-key"),
        ):
            app._worker(
                "generate",
                run_live_generation,
                ("", "secret-test-key", "model", {}, {}),
            )

        action, result_type, message = app.results.get_nowait()
        self.assertEqual((action, result_type), ("generate", "error"))
        self.assertIn("Unexpected OSError", message)
        self.assertIn("[redacted API key]", message)
        self.assertNotIn("secret-test-key", message)

    def test_ui_live_generation_uses_agent_and_returns_drafts(self):
        event = {"title": "Upcoming event"}
        assets = {"linkedin": "post", "twitter": "tweet", "email_newsletter": "email"}
        options = {"channels": ["linkedin"]}
        with patch("ui.genai.Client") as client_factory, patch(
            "ui.GDGEventMarketingAgent"
        ) as agent_factory:
            agent_factory.return_value.fetch_latest_event.return_value = event
            agent_factory.return_value.generate_content.return_value = assets

            result = run_live_generation("123", "test-key", "test-model", event, options)

        client_factory.assert_called_once_with(api_key="test-key")
        agent_factory.assert_called_once_with(
            "123",
            client_factory.return_value,
            "test-model",
        )
        agent_factory.return_value.generate_content.assert_called_once_with(event, **options)
        self.assertEqual(result, (event, assets))

    def test_demo_event_and_content_are_fictional_samples(self):
        event = build_demo_event()
        assets = build_demo_content(event)

        self.assertEqual(event["chapter_id"], DEMO_CHAPTER_ID)
        self.assertIn("fictional", event["url"])
        self.assertEqual(
            set(assets),
            {"linkedin", "twitter", "email_newsletter"},
        )
        self.assertTrue(all(event["title"] in draft for draft in assets.values()))
        self.assertTrue(all("fictional" in draft.lower() for draft in assets.values()))
        self.assertTrue(all(event["url"] in draft for draft in assets.values()))
        self.assertIn("📅", assets["linkedin"])
        self.assertIn("Preheader:", assets["email_newsletter"])
        self.assertLessEqual(len(assets["twitter"]), 280)

    def test_visual_carousel_uses_event_draft_and_escapes_user_content(self):
        event = {
            "title": "A <curious> event",
            "date_time": "2026-11-10 18:00 UTC",
            "location": "Online",
            "speakers": "Community team",
            "url": "https://example.test/event?a=1&b=2",
        }
        draft = (
            "Curious about open source?\n\n"
            "Explore practical ideas with your community.\n\n"
            "Join us here: https://example.test/event?a=1&b=2\n\n"
            "#Community"
        )

        slides = build_carousel_slides(event, draft)
        page = render_carousel_html(event, draft)

        self.assertEqual(len(slides), 4)
        self.assertIn("Curious about open source?", slides[0]["body"])
        self.assertIn("Explore practical ideas", slides[1]["body"])
        self.assertIn("2026-11-10 18:00 UTC", slides[2]["body"])
        self.assertIn("https://example.test/event?a=1&b=2", slides[3]["body"])
        self.assertIn("Download this card as PNG", page)
        self.assertIn("Print / Save as PDF", page)
        self.assertIn("A &lt;curious&gt; event", page)
        self.assertNotIn("<curious>", page)
        self.assertNotIn('src="https://', page)
        self.assertIn('aria-label="Carousel cover for A &lt;curious&gt; event"', page)

    def test_campaign_plan_builds_event_anchored_stages_and_calendar_reminders(self):
        event = {
            "title": "Community AI Night",
            "date_time": "2026-11-07T17:00:00+05:30",
            "location": "Bengaluru",
            "description": "A community session about practical AI tools.",
            "url": "https://example.test/event",
        }

        campaign = build_event_campaign(event)
        calendar = build_campaign_ics(event, campaign)

        self.assertEqual(
            [item["stage"] for item in campaign],
            [
                "Announcement",
                "Topic spotlight",
                "One-day reminder",
                "Post-event follow-up",
            ],
        )
        self.assertEqual(
            [item["offset_days"] for item in campaign],
            [-14, -7, -1, 1],
        )
        self.assertTrue(all(event["title"] in item["copy"] for item in campaign))
        self.assertIn("real moment", campaign[-1]["copy"])
        self.assertEqual(calendar.count("BEGIN:VEVENT"), 4)
        self.assertEqual(calendar.count("END:VEVENT"), 4)
        self.assertIn("Review and manually publish", calendar)
        self.assertIn("nothing will be posted automatically", calendar)
        self.assertIn("DTSTART:", calendar)
        self.assertNotIn("ATTENDEE:", calendar)

    def test_campaign_plan_requires_timezone_and_valid_event_details(self):
        event = {
            "title": "Community AI Night",
            "date_time": "2026-11-07 17:00",
            "description": "A community session about practical AI tools.",
        }
        with self.assertRaisesRegex(ValueError, "time-zone offset"):
            build_event_campaign(event)

        event["date_time"] = "not a date"
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            build_event_campaign(event)

    def test_campaign_calendar_escapes_user_event_title(self):
        event = {
            "title": "Community Night\r\nATTENDEE:mailto:unexpected@example.test",
            "date_time": "2026-11-07T17:00:00Z",
            "description": "A community event.",
        }

        calendar = build_campaign_ics(event, build_event_campaign(event))
        unfolded_calendar = calendar.replace("\r\n ", "")

        self.assertNotIn("\r\nATTENDEE:", calendar)
        self.assertIn(
            r"\nATTENDEE:mailto:unexpected@example.test", unfolded_calendar
        )

    def test_demo_mode_runs_without_network_or_gemini(self):
        output = StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch("sys.argv", ["agent.py", "--demo"]))
            get = stack.enter_context(patch("agent.requests.get"))
            client = stack.enter_context(patch("agent.genai.Client"))
            stack.enter_context(redirect_stdout(output))
            result = main()

        self.assertEqual(result, 0)
        get.assert_not_called()
        client.assert_not_called()
        self.assertIn("OFFLINE DEMO MODE", output.getvalue())
        self.assertIn("--- LINKEDIN POST (SAMPLE) ---", output.getvalue())
        self.assertIn("--- X POST (SAMPLE) ---", output.getvalue())
        self.assertIn("--- EMAIL NEWSLETTER (SAMPLE) ---", output.getvalue())

    def test_fetch_latest_event_returns_event_details(self):
        response = Mock()
        response.json.return_value = {
            "results": [
                {
                    "title": "Later event",
                    "start_date": "2099-12-01T18:00:00+00:00",
                    "speakers": [],
                    "url": "https://gdg.community.dev/event/later/",
                },
                {
                    "title": "Community AI Night",
                    "start_date": "2099-11-01T18:00:00Z",
                    "speakers": [{"name": "Alex"}],
                    "description_short": "A community meetup",
                    "url": "https://gdg.community.dev/event/example/",
                    "city": "Bengaluru",
                },
                {
                    "title": "Past event",
                    "start_date": "2000-01-01T18:00:00Z",
                },
            ]
        }
        agent = GDGEventMarketingAgent("123", Mock(), "test-model")

        with patch("agent.requests.get", return_value=response) as get:
            event = agent.fetch_latest_event()

        get.assert_called_once_with(
            "https://gdg.community.dev/api/event/",
            params={"chapter": "123", "status": "Published", "page_size": 1},
            timeout=30,
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(event["title"], "Community AI Night")
        self.assertEqual(event["speakers"], "Alex")
        self.assertEqual(event["location"], "Bengaluru")

    def test_fetch_upcoming_events_sorts_dates_and_skips_invalid_or_past(self):
        response = Mock()
        response.json.return_value = {
            "results": [
                {"title": "Later", "start_date": "2099-12-01T18:00:00+00:00"},
                {"title": "Past", "start_date": "2000-01-01T18:00:00Z"},
                {"title": "Sooner", "start_date": "2099-11-01T18:00:00Z"},
                {"title": "Invalid", "start_date": "not-a-date"},
                {"title": "Missing date"},
            ]
        }
        with patch("agent.requests.get", return_value=response) as get:
            events = fetch_upcoming_events("123", limit=5)

        self.assertEqual([event["title"] for event in events], ["Sooner", "Later"])
        get.assert_called_once_with(
            "https://gdg.community.dev/api/event/",
            params={"chapter": "123", "status": "Published", "page_size": 5},
            timeout=30,
        )

    def test_fetch_latest_event_returns_empty_dict_when_no_upcoming_events(self):
        response = Mock()
        response.json.return_value = {
            "results": [
                {"title": "Past event", "start_date": "2000-01-01T18:00:00Z"}
            ]
        }
        agent = GDGEventMarketingAgent("123", Mock(), "test-model")

        with patch("agent.requests.get", return_value=response):
            self.assertEqual(agent.fetch_latest_event(), {})

    def test_generate_content_creates_all_three_assets(self):
        models = Mock()
        models.generate_content.return_value = SimpleNamespace(text="Generated draft")
        agent = GDGEventMarketingAgent(
            "123",
            SimpleNamespace(models=models),
            "test-model",
        )

        assets = agent.generate_content({"title": "Community AI Night"})

        self.assertEqual(
            set(assets),
            {"linkedin", "twitter", "email_newsletter"},
        )
        self.assertEqual(models.generate_content.call_count, 3)
        for call in models.generate_content.call_args_list:
            self.assertEqual(call.kwargs["model"], "test-model")
            self.assertIsInstance(call.kwargs["config"], types.GenerateContentConfig)
            self.assertIn("Community AI Night", call.kwargs["contents"])
            self.assertIn("Do not imply", call.kwargs["config"].system_instruction)

    def test_generate_content_supports_selected_channels_and_preferences(self):
        models = Mock()
        models.generate_content.return_value = SimpleNamespace(text="Generated draft")
        agent = GDGEventMarketingAgent("123", SimpleNamespace(models=models), "test-model")

        assets = agent.generate_content(
            {"title": "Community AI Night"},
            tone="Energetic",
            audience="First-time attendees",
            call_to_action="Register today",
            custom_instructions="Keep it accessible",
            channels=["linkedin"],
        )

        self.assertEqual(assets, {"linkedin": "Generated draft"})
        self.assertEqual(models.generate_content.call_count, 1)
        prompt = models.generate_content.call_args.kwargs["contents"]
        self.assertIn("Tone: Energetic", prompt)
        self.assertIn("Audience: First-time attendees", prompt)
        self.assertIn("Call to action: Register today", prompt)
        self.assertIn("Keep it accessible", prompt)

    def test_generate_content_rejects_empty_or_unknown_channel_selection(self):
        agent = GDGEventMarketingAgent("123", Mock(), "test-model")
        with self.assertRaises(ValueError):
            agent.generate_content({}, channels=[])
        with self.assertRaises(ValueError):
            agent.generate_content({}, channels=["unknown"])


if __name__ == "__main__":
    unittest.main()

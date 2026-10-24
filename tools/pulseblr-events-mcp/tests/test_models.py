import unittest

from pulseblr_events_mcp.errors import SourceError
from pulseblr_events_mcp.models import normalize_event


class PublicEventTests(unittest.TestCase):
    def event(self, **changes):
        return {
            "id": "sample-1",
            "title": "Example AI meetup",
            "url": "https://example.com/events/sample-1",
            "startsAt": "2026-10-24T09:00:00+05:30",
            "format": "offline",
            **changes,
        }

    def test_public_fields_only_and_no_unknown_cost_inference(self):
        result = normalize_event(self.event(email="PRIVATE", apiKey="PRIVATE", notes="PRIVATE"))
        self.assertNotIn("email", result)
        self.assertNotIn("apiKey", result)
        self.assertNotIn("notes", result)
        self.assertNotIn("isFree", result)

    def test_requires_aware_time_and_safe_urls(self):
        for changes in (
            {"startsAt": "2026-10-24T09:00:00"},
            {"url": "https://name:secret@example.com/event"},
            {"url": "file:///private/data"},
            {"id": "../../personal"},
        ):
            with self.subTest(changes=changes), self.assertRaises(SourceError):
                normalize_event(self.event(**changes))

    def test_text_and_sensitive_link_values_are_bounded(self):
        result = normalize_event(
            self.event(
                description="a" * 9000,
                registerUrl="https://example.com/register?token=PRIVATE&event=abc",
                sourceUrl="https://name:PRIVATE@example.com/event",
            )
        )
        self.assertLessEqual(len(result["description"]), 1200)
        self.assertNotIn("PRIVATE", str(result))

    def test_huge_numeric_score_is_bounded_without_overflow(self):
        self.assertEqual(
            normalize_event(self.event(connectionScore=10**1000))["connectionScore"], 100
        )

    def test_invalid_end_remains_unknown_duration_without_echoing_bad_value(self):
        result = normalize_event(self.event(endsAt="PRIVATE_INVALID_END"))
        self.assertNotIn("endsAt", result)
        self.assertEqual(result["endTimeStatus"], "invalid")
        self.assertNotIn("PRIVATE_INVALID_END", str(result))
        self.assertEqual(normalize_event(result)["endTimeStatus"], "invalid")


if __name__ == "__main__":
    unittest.main()

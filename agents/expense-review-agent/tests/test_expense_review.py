"""Offline regressions for source ingestion and the human approval gate."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from expense_review.agent import DEFAULT_MODEL, ExpenseAgent, GeminiConfigurationError, GeminiExtractor
from expense_review.connectors import import_keep
from expense_review.ledger import Ledger, guardrails
from expense_review.models import Extraction, Proposal, SourceNote


class ExpenseReviewChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.ledger = Ledger(Path(self.folder.name) / "ledger.sqlite3")
        self.note = SourceNote(source="manual", source_id="synthetic", title="Lunch",
                               text="On 2026-10-20 I paid INR 250 for lunch.")
        self.proposal = Proposal(transaction_date="2026-10-20", amount="250", currency="INR",
                                 kind="spending", category="Food", counterparty="Cafe",
                                 reason="The source explicitly records a completed lunch payment.",
                                 evidence=self.note.text, confidence=0.95)

    def stage(self, note=None, proposal=None):
        note_id, _ = self.ledger.add_note(note or self.note)
        self.ledger.stage(note_id, [proposal or self.proposal], "One supported transaction.")
        return self.ledger.snapshot()["candidates"][0]["id"]

    def test_model_proposals_never_enter_totals_without_review(self):
        candidate = self.stage()
        self.assertEqual(self.ledger.monthly("2026-10")["approved_count"], 0)
        self.ledger.review(candidate, "approved", "Checked the original note.")
        result = self.ledger.monthly("2026-10")
        self.assertEqual(result["totals"]["spending"], "250")
        self.assertEqual(result["net_cashflow"], "-250")
        self.assertEqual(len(self.ledger.snapshot()["audit"]), 1)
        with self.assertRaisesRegex(ValueError, "already reviewed"):
            self.ledger.review(candidate, "approved", "Trying to approve twice.")

    def test_import_and_staging_are_idempotent(self):
        note_id, first = self.ledger.add_note(self.note)
        _, second = self.ledger.add_note(self.note)
        self.assertTrue(first)
        self.assertFalse(second)
        self.ledger.stage(note_id, [self.proposal], "One transaction.")
        self.ledger.stage(note_id, [self.proposal], "Same transaction.")
        self.assertEqual(len(self.ledger.snapshot()["candidates"]), 1)

    def test_blocking_guardrails_require_correction(self):
        for change, flag in [({"amount": "999"}, "amount_not_in_evidence"),
                             ({"currency": "USD"}, "unsupported_currency"),
                             ({"kind": "unknown"}, "unknown_direction"),
                             ({"evidence": "250 invented"}, "evidence_not_in_source")]:
            corrected = Proposal.model_validate({**self.proposal.model_dump(), **change})
            self.assertIn(flag, guardrails(corrected, self.note))
            candidate = self.stage()
            with self.assertRaisesRegex(ValueError, flag):
                self.ledger.review(candidate, "approved", "Checked the source document.", corrected)

    def test_same_date_and_amount_require_duplicate_confirmation(self):
        first = self.stage()
        self.ledger.review(first, "approved", "Checked first source.")
        other = self.note.model_copy(update={"source_id": "different-source"})
        self.stage(other)
        second = next(row["id"] for row in self.ledger.snapshot()["candidates"] if row["status"] == "pending")
        with self.assertRaisesRegex(ValueError, "Possible duplicate"):
            self.ledger.review(second, "approved", "Checked second source.")
        self.ledger.review(second, "approved", "Confirmed a distinct payment.", confirm_duplicate=True)
        self.assertEqual(self.ledger.monthly("2026-10")["approved_count"], 2)

    def test_lending_and_borrowing_are_not_expense_categories(self):
        lending = Proposal.model_validate({**self.proposal.model_dump(), "kind": "lending"})
        candidate = self.stage(proposal=lending)
        self.ledger.review(candidate, "approved", "Verified the lending transaction.")
        result = self.ledger.monthly("2026-10")
        self.assertEqual(result["totals"]["lending"], "250")
        self.assertEqual(result["totals"]["spending"], "0")
        self.assertEqual(result["categories"], {})
        borrowing = Proposal.model_validate({**self.proposal.model_dump(), "kind": "borrowing", "amount": "500",
                                            "evidence": "Received INR 500 on 2026-10-20 as a loan."})
        other = self.note.model_copy(update={"source_id": "loan", "text": borrowing.evidence})
        self.stage(other, borrowing)
        candidate = next(row["id"] for row in self.ledger.snapshot()["candidates"] if row["status"] == "pending")
        self.ledger.review(candidate, "approved", "Verified the borrowing transaction.")
        self.assertEqual(self.ledger.monthly("2026-10")["net_cashflow"], "250")

    def test_keep_checklists_and_schema_validation(self):
        notes = import_keep({"title": "Transactions", "textContent": "", "listContent": [{"text": self.note.text}]})
        self.assertEqual(notes[0].text, self.note.text)
        self.assertEqual(import_keep({"isTrashed": True}), [])
        with self.assertRaises(ValidationError):
            Proposal.model_validate({**self.proposal.model_dump(), "amount": "-1"})
        with self.assertRaises(ValidationError):
            Extraction.model_validate({"transactions": [], "explanation": "", "approved": True})

    def test_bad_model_output_stays_visible_as_error(self):
        class InvalidExtractor:
            async def extract(self, note):
                raise ValueError("Invalid schema")

        agent = ExpenseAgent(self.ledger, InvalidExtractor())
        agent.ingest([self.note])
        result = asyncio.run(agent.reason())
        self.assertEqual(result["errors"], 1)
        self.assertEqual(self.ledger.snapshot()["notes"][0]["state"], "error")
        self.assertEqual(self.ledger.monthly("2026-10")["approved_count"], 0)


class GeminiExtractorChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.note = SourceNote(source="manual", source_id="synthetic", title="Lunch",
                               text="On 2026-10-20 I paid INR 250 for lunch.")
        self.extraction = Extraction(transactions=[], explanation="No fixture transactions.")
        environment = patch.dict(os.environ, {"GEMINI_API_KEY": "offline-dummy-key", "GEMINI_MODEL": DEFAULT_MODEL})
        environment.start()
        self.addCleanup(environment.stop)

    async def extract_response(self, payload, status_code=200):
        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, json=payload),
        ))
        with patch("expense_review.agent.httpx.AsyncClient", return_value=client):
            return await GeminiExtractor().extract(self.note)

    async def test_https_request_uses_header_key_and_structured_output(self):
        def respond(request):
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.host, "generativelanguage.googleapis.com")
            self.assertEqual(request.url.query, b"")
            self.assertNotIn("offline-dummy-key", str(request.url))
            self.assertEqual(request.headers["x-goog-api-key"], "offline-dummy-key")
            body = json.loads(request.content)
            self.assertEqual(json.loads(body["contents"][0]["parts"][0]["text"]), self.note.model_dump())
            self.assertEqual(body["generationConfig"]["maxOutputTokens"], 3000)
            self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["schema"], Extraction.model_json_schema())
            return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"text": "untrusted internal thought", "thought": True},
                {"text": self.extraction.model_dump_json()},
            ]}}]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("expense_review.agent.httpx.AsyncClient", return_value=client):
            result = await GeminiExtractor().extract(self.note)
        self.assertEqual(result, self.extraction)

    def test_missing_key_and_invalid_model_fail_before_network_access(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(GeminiConfigurationError, "GEMINI_API_KEY"):
                GeminiExtractor()
        for model in ("qwen3:4b", "../unexpected", "https://untrusted.example/model"):
            with self.assertRaisesRegex(ValueError, "valid Gemini model"):
                GeminiExtractor(model)

    async def test_blocked_truncated_and_missing_candidates_are_rejected(self):
        for payload in ({"promptFeedback": {"blockReason": "SAFETY"}},
                        {"candidates": []},
                        {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [
                            {"text": self.extraction.model_dump_json()},
                        ]}}]}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    await self.extract_response(payload)

    async def test_invalid_json_and_schema_output_are_rejected(self):
        for text in ("not json", '{"transactions": [], "explanation": ""}'):
            with self.subTest(text=text):
                with self.assertRaises(ValidationError):
                    await self.extract_response({"candidates": [{"finishReason": "STOP", "content": {
                        "parts": [{"text": text}],
                    }}]})

    async def test_rate_limit_stays_in_error_queue_without_leaking_key(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / "ledger.sqlite3")
            agent = ExpenseAgent(ledger, GeminiExtractor())
            agent.ingest([self.note])
            client = httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(429, json={"error": {"message": "private provider detail"}}),
            ))
            with patch("expense_review.agent.httpx.AsyncClient", return_value=client):
                result = await agent.reason()
            self.assertEqual(result["errors"], 1)
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot["candidates"], [])
            self.assertIn("HTTP 429", snapshot["notes"][0]["explanation"])
            self.assertNotIn("offline-dummy-key", json.dumps(snapshot))
            self.assertNotIn("private provider detail", json.dumps(snapshot))


if __name__ == "__main__":
    unittest.main()
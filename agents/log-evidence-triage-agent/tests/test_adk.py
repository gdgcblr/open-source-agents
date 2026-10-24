"""Optional offline integration evaluations against the real ADK runner."""
import asyncio
from datetime import date
import json
import io
import logging
import os
import unittest
from unittest.mock import patch

from incident_triage.ai import enhance, model_bundle
from incident_triage.credibility import apply_candidate
from incident_triage.investigation import investigate

try:
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from incident_triage.adk_adapter import select_findings
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False


if ADK_AVAILABLE:
    class FixtureModel(BaseLlm):
        model: str = "offline_fixture"
        behavior: str = "valid"

        async def generate_content_async(self, llm_request, stream=False):
            if self.behavior == "failure":
                raise RuntimeError("Synthetic provider failure with private-key")
            bundle = None
            for content in llm_request.contents:
                for part in content.parts or []:
                    if part.function_response:
                        bundle = part.function_response.response
            if bundle is None and self.behavior != "skip_tool":
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(
                    function_call=types.FunctionCall(name="get_verified_findings", args={}))]))
            else:
                if self.behavior == "fabricate":
                    bundle = {"decision": "PASS", "claims": [{"id": "F900", "text": "Confirmed compromise", "evidence_refs": ["L900"]}]}
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(bundle or {}))]))


@unittest.skipUnless(ADK_AVAILABLE, "Optional ADK dependencies not installed")
class AdkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"GOOGLE_API_KEY": "", "MODEL_NAME": "offline_fixture"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.report = investigate("INFO ready", "php", "8.4.26", today=date(2026, 10, 24))

    async def test_real_runner_calls_tool_and_returns_grounded_selection(self):
        bundle = model_bundle(self.report)
        result = await select_findings(bundle, model=FixtureModel())
        self.assertEqual(result, bundle)
        self.assertEqual(apply_candidate(self.report, result)["mode"], "ai_assisted_validated")

    async def test_real_runner_fabrication_rejected(self):
        result = await select_findings(model_bundle(self.report), model=FixtureModel(behavior="fabricate"))
        checked = apply_candidate(self.report, result)
        self.assertEqual(checked["decision"], "ESCALATE")
        self.assertEqual(checked["mode"], "offline_fallback")

    async def test_real_runner_requires_tool_call(self):
        result = await select_findings(model_bundle(self.report), model=FixtureModel(behavior="skip_tool"))
        self.assertEqual(apply_candidate(self.report, result)["mode"], "offline_fallback")

    async def test_real_runner_api_failure_falls_back(self):
        async def responder(bundle):
            return await select_findings(bundle, model=FixtureModel(behavior="failure"))
        captured = io.StringIO()
        handler = logging.StreamHandler(captured)
        logging.getLogger().addHandler(handler)
        try:
            result = await enhance(self.report, responder)
        finally:
            logging.getLogger().removeHandler(handler)
        self.assertEqual(result["mode"], "offline_fallback")
        self.assertNotIn("private-key", json.dumps(result))
        self.assertNotIn("private-key", captured.getvalue())

    async def test_concurrent_sessions_do_not_share_evidence(self):
        other = investigate("INFO ready", "nodejs", "22.23.4", today=date(2026, 10, 24))
        first, second = await asyncio.gather(
            select_findings(model_bundle(self.report), model=FixtureModel()),
            select_findings(model_bundle(other), model=FixtureModel()))
        self.assertEqual(first["decision"], "ESCALATE")
        self.assertEqual(second["decision"], "PASS")
        self.assertNotEqual(first["claims"], second["claims"])

    async def test_public_agent_holds_invalid_request_without_leaking(self):
        from incident_triage.agent import TraceGuardAgent
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name="test_traceguard", user_id="local")
        runner = Runner(agent=TraceGuardAgent(name="test_traceguard"), app_name="test_traceguard", session_service=sessions)
        try:
            for message in ['{"filename":"../../private-secret.log"}', '{"log_text": null}']:
                async for event in runner.run_async(user_id="local", session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part(text=message)])):
                    if event.is_final_response():
                        result = json.loads(event.content.parts[0].text)
                        self.assertEqual(result["decision"], "HOLD")
                        self.assertNotIn("private-secret", json.dumps(result))
        finally:
            await runner.close()

    async def test_public_agent_missing_key_uses_offline_report(self):
        from incident_triage.agent import TraceGuardAgent
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name="test_traceguard", user_id="local")
        runner = Runner(agent=TraceGuardAgent(name="test_traceguard"), app_name="test_traceguard", session_service=sessions)
        try:
            message = json.dumps({"log_text": "INFO ready", "product": "php", "version": "8.4.26"})
            async for event in runner.run_async(user_id="local", session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text=message)])):
                if event.is_final_response():
                    result = json.loads(event.content.parts[0].text)
                    self.assertEqual(result["decision"], "ESCALATE")
                    self.assertEqual(result["mode"], "offline_fallback")
        finally:
            await runner.close()


for name in [n for n in dir(AdkTests) if n.startswith("test_")]:
    getattr(AdkTests, name).metric = "adk_offline_integration"

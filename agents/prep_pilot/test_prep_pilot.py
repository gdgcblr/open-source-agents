import importlib
import unittest

from google.adk.agents import Agent


class PrepPilotAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent_module = importlib.import_module("prep_pilot.agent")

    def test_exports_gemini_only_root_agent(self):
        agent = self.agent_module.root_agent

        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.name, "prep_pilot")
        self.assertEqual(agent.model, "gemini-3.5-flash")
        self.assertEqual(agent.tools, [])

    def test_instruction_covers_candidate_journey_and_evidence(self):
        instruction = " ".join(self.agent_module.root_agent.instruction.split())

        for required_guidance in (
            "one or two concise questions",
            "You do not have web search",
            "day-by-day plan",
            "adapt difficulty",
            "real-time stopwatch",
            "Never invent sources",
        ):
            with self.subTest(guidance=required_guidance):
                self.assertIn(required_guidance, instruction)


if __name__ == "__main__":
    unittest.main()

"""Smoke tests for the agent <-> automation-layer integration.

Run from the project root:   python -m unittest discover -s tests -v

What runs where:
  * Always: adapter structure, docstrings, instruction rules, guard logic, and
    real calls into the real AndroidAutomation layer. Without adb or a device
    those calls return the layer's genuine failure responses (for example
    ADB_NOT_FOUND), which still exercises the structured-response path.
  * Only with a connected, authorised device/emulator: live read-only checks.
  * Only with google-adk installed: the root agent is built and inspected.

Nothing here fakes Android behaviour.
"""

import importlib.util
import inspect
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import callbacks, config, prompts, tools  # noqa: E402

REQUIRED_KEYS = {"success", "action", "message", "data"}


def _device_ready() -> bool:
    result = tools.list_devices()
    return bool(result["success"]) and any(
        d.get("state") == "device" for d in result["data"].get("devices", [])
    )


DEVICE_READY = _device_ready()
ADK_INSTALLED = importlib.util.find_spec("google.adk") is not None


class AdapterStructureTests(unittest.TestCase):
    def test_every_tool_is_documented_for_the_llm(self):
        for fn in tools.ANDROID_TOOLS:
            with self.subTest(tool=fn.__name__):
                doc = inspect.getdoc(fn) or ""
                self.assertGreater(len(doc), 40, "docstring too short for an LLM tool")
                for param in inspect.signature(fn).parameters.values():
                    self.assertIsNot(param.annotation, inspect.Parameter.empty,
                                     f"{param.name} needs a type hint")
                    if len(inspect.signature(fn).parameters) > 1 and param.name != "self":
                        self.assertIn(param.name, doc, f"{param.name} not described")

    def test_tool_names_are_unique(self):
        names = [fn.__name__ for fn in tools.ANDROID_TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_adapter_only_exposes_primitives_of_the_automation_layer(self):
        automation = tools.get_automation()
        layer_tools = set(sys.modules["android_ui_automation"].TOOL_NAMES)
        adapter_only = {"find_installed_package"}
        for fn in tools.ANDROID_TOOLS:
            if fn.__name__ not in adapter_only:
                self.assertIn(fn.__name__, layer_tools)
        self.assertTrue(hasattr(automation, "call"))

    def test_instruction_has_no_adk_placeholders(self):
        text = prompts.build_instruction(2, 40)
        self.assertNotIn("{", text)
        self.assertNotIn("}", text)
        self.assertIn("at most 2 times", text)
        self.assertIn("40 tool calls", text)


class RealLayerIntegrationTests(unittest.TestCase):
    def test_results_are_json_serialisable_structured_dicts(self):
        for result in (tools.is_device_connected(), tools.list_devices()):
            self.assertIsInstance(result, dict)
            self.assertTrue(REQUIRED_KEYS <= result.keys())
            json.dumps(result)
            if not result["success"]:
                self.assertIn("code", result["error"])

    def test_failure_responses_keep_error_codes(self):
        result = tools.launch_app("not a valid package!")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")

    def test_element_compaction_on_real_layer_parser_output(self):
        # Parse uiautomator-format XML with the layer's real parser, then compact.
        tools.get_automation()  # ensures the layer is loaded under its alias
        parse = sys.modules["android_ui_automation.ui.hierarchy"].parse_hierarchy
        xml = (
            '<hierarchy rotation="0"><node index="0" text="" resource-id="com.x:id/url_bar" '
            'class="android.widget.EditText" package="com.x" content-desc="" clickable="true" '
            'enabled="true" focused="false" scrollable="false" password="false" '
            'hint="Search or type URL" bounds="[0,100][1080,200]"/></hierarchy>'
        )
        el = parse(xml).elements[0].to_dict()
        compact = tools._compact_element(el)
        self.assertEqual(compact["resource_id"], "com.x:id/url_bar")
        self.assertEqual(compact["class"], "EditText")
        self.assertEqual(compact["hint"], "Search or type URL")
        self.assertEqual(compact["center"], [540, 150])
        self.assertNotIn("text", compact)          # empty values are dropped
        self.assertNotIn("bounds", compact)

    def test_text_verification_failure_gets_inconclusive_note(self):
        # Use the adapter's real shaping path on a real-layer-shaped response.
        self.assertIn("INCONCLUSIVE", tools._AGENT_NOTES["TEXT_VERIFICATION_FAILED"])

    @unittest.skipUnless(DEVICE_READY, "no authorised Android device/emulator connected")
    def test_live_read_only_calls(self):
        self.assertTrue(tools.is_device_connected()["data"]["connected"])
        size = tools.get_screen_size()
        self.assertTrue(size["success"], size)
        hierarchy = tools.get_ui_hierarchy(max_elements=5)
        self.assertTrue(hierarchy["success"], hierarchy)
        self.assertLessEqual(len(hierarchy["data"]["elements"]), 5)
        json.dumps(hierarchy)


class GuardTests(unittest.TestCase):
    """Budget/retry logic with stand-in ADK context objects (pure Python)."""

    def setUp(self):
        self.settings = config.Settings(max_retries=1, max_tool_calls=4)
        config._SETTINGS = self.settings
        self.addCleanup(lambda: setattr(config, "_SETTINGS", None))
        self.ctx = SimpleNamespace(state={}, invocation_id="inv-1")
        self.tool = SimpleNamespace(name="click_element")
        self.args = {"text": "Login"}
        self.failure = {"success": False, "error": {"code": "ELEMENT_NOT_FOUND", "details": "x"}}

    def _attempt(self, response):
        refusal = callbacks.before_tool_callback(self.tool, self.args, self.ctx)
        if refusal is None:
            callbacks.after_tool_callback(self.tool, self.args, self.ctx, response)
        return refusal

    def test_identical_failures_are_cut_off_after_retry_budget(self):
        self.assertIsNone(self._attempt(self.failure))      # attempt 1
        self.assertIsNone(self._attempt(self.failure))      # retry 1 (max_retries=1)
        refusal = self._attempt(self.failure)               # would be retry 2
        self.assertEqual(refusal["error"]["code"], callbacks.RETRY_LIMIT)

    def test_success_resets_the_streak(self):
        self._attempt(self.failure)
        self._attempt({"success": True})
        self.assertIsNone(self._attempt(self.failure))
        self.assertIsNone(self._attempt(self.failure))

    def test_total_tool_call_budget(self):
        for i in range(4):
            self.assertIsNone(
                callbacks.before_tool_callback(SimpleNamespace(name=f"t{i}"), {}, self.ctx)
            )
        refusal = callbacks.before_tool_callback(SimpleNamespace(name="t5"), {}, self.ctx)
        self.assertEqual(refusal["error"]["code"], callbacks.BUDGET_EXCEEDED)

    def test_budget_resets_for_a_new_request(self):
        for i in range(4):
            callbacks.before_tool_callback(SimpleNamespace(name=f"t{i}"), {}, self.ctx)
        self.ctx.invocation_id = "inv-2"
        self.assertIsNone(callbacks.before_tool_callback(self.tool, self.args, self.ctx))

    def test_typed_text_is_not_logged_by_default(self):
        redacted = callbacks.redact_args("input_text", {"text": "secret-password", "hint": "Email"})
        self.assertEqual(redacted["text"], "<15 chars>")
        self.assertEqual(redacted["hint"], "Email")


@unittest.skipUnless(ADK_INSTALLED, "google-adk is not installed")
class AgentWiringTests(unittest.TestCase):
    def test_root_agent_has_all_tools_and_callbacks(self):
        from src.agent import root_agent

        self.assertEqual(root_agent.name, "android_automation_agent")
        self.assertEqual(len(root_agent.tools), len(tools.ANDROID_TOOLS))
        self.assertIsNotNone(root_agent.before_tool_callback)
        self.assertIsNotNone(root_agent.after_tool_callback)


if __name__ == "__main__":
    unittest.main()

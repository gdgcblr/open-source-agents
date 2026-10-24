import unittest

from breaker import CircuitBreaker, canonical
from dlp import check_args, redact, redact_obj

# Synthetic, non-functional credentials built at runtime so scanners don't flag the file.
FAKE_OPENAI = "sk-" + "FAKEfake" * 3
FAKE_GITHUB = "ghp_" + "A1" * 18
FAKE_AWS = "AKIA" + "FAKE" * 4
FAKE_BEARER = "Bearer " + "fake.token." * 3


class BreakerTests(unittest.TestCase):
    def test_repeated_identical_call_blocked_on_third(self):
        b = CircuitBreaker()
        self.assertTrue(b.check("search", {"q": "x"}).allowed)
        self.assertTrue(b.check("other", {}).allowed)
        self.assertTrue(b.check("search", {"q": "x"}).allowed)
        d = b.check("search", {"q": "x"})
        self.assertEqual((d.allowed, d.code), (False, "repeat"))

    def test_argument_key_order_is_normalized(self):
        self.assertEqual(canonical("t", {"a": 1, "b": [1, 2]}), canonical("t", {"b": [1, 2], "a": 1}))
        self.assertNotEqual(canonical("t", {"a": 1}), canonical("t", {"a": 2}))

    def test_abab_cycle_blocked(self):
        b = CircuitBreaker()
        for tool in "ABA":
            self.assertTrue(b.check(tool, {}).allowed)
        d = b.check("B", {})
        self.assertEqual((d.allowed, d.code), (False, "cycle"))

    def test_non_cycle_sequence_allowed(self):
        b = CircuitBreaker()
        for tool in "ABCDE":
            self.assertTrue(b.check(tool, {}).allowed)

    def test_consecutive_errors_trip_and_success_resets(self):
        b = CircuitBreaker(max_errors=3)
        for i in range(2):
            b.check(f"t{i}", {})
            b.record_result(False)
        b.record_result(True)
        self.assertTrue(b.check("t2", {}).allowed)
        for _ in range(3):
            b.record_result(False)
        d = b.check("t3", {})
        self.assertEqual((d.allowed, d.code), (False, "errors"))

    def test_call_budget_exhausted(self):
        b = CircuitBreaker(max_calls=5)
        for i in range(5):
            self.assertTrue(b.check("t", {"i": i}).allowed)
        d = b.check("t", {"i": 99})
        self.assertEqual((d.allowed, d.code), (False, "budget"))

    def test_default_budget_is_20(self):
        b = CircuitBreaker()
        results = [b.check("t", {"i": i}).allowed for i in range(21)]
        self.assertEqual(results.count(True), 20)

    def test_sessions_are_independent(self):
        a, b = CircuitBreaker(), CircuitBreaker()
        a.check("x", {})
        a.check("x", {})
        a.record_result(False)
        self.assertFalse(a.check("x", {}).allowed)
        self.assertTrue(b.check("x", {}).allowed)
        self.assertEqual(b.consecutive_errors, 0)


class DlpTests(unittest.TestCase):
    def test_redacts_each_secret_type(self):
        for secret, label in [(FAKE_OPENAI, "openai_key"), (FAKE_GITHUB, "github_token"),
                              (FAKE_AWS, "aws_access_key"), (FAKE_BEARER, "bearer_token")]:
            out, found = redact(f"value: {secret} end")
            self.assertNotIn(secret, out)
            self.assertIn(f"[REDACTED:{label}]", out)
            self.assertEqual(found, [label])

    def test_redact_nested_args(self):
        out, found = redact_obj({"headers": {"auth": FAKE_BEARER}, "list": [FAKE_AWS, 3]})
        self.assertNotIn(FAKE_AWS, str(out))
        self.assertEqual(out["list"][1], 3)
        self.assertEqual(sorted(found), ["aws_access_key", "bearer_token"])

    def test_ordinary_text_preserved(self):
        text = "Ask the bearer of news. Task-list sk-ip AKIA short. ghp_ alone."
        self.assertEqual(redact(text), (text, []))

    def test_dangerous_args_detected(self):
        cases = {
            "env_file_access": [{"path": ".env"}, {"path": "app/.env.local"}, {"cmd": "cat .env"}],
            "path_traversal": [{"path": "../../etc/passwd"}, {"path": "a\\..\\b"}],
            "destructive_command": [{"cmd": "rm -rf /"}, {"cmd": "sudo rm -fr ~"}, {"sql": "DROP TABLE users"},
                                    {"cmd": "dd if=/dev/zero of=/dev/sda"}],
        }
        for label, argsets in cases.items():
            for args in argsets:
                self.assertIn(label, check_args(args), args)

    def test_safe_args_pass(self):
        for args in [{"path": ".env.example"}, {"path": "src/environment.py"}, {"cmd": "ls -la"},
                     {"path": "notes..txt"}]:
            self.assertEqual(check_args(args), [], args)


class BreakerBoundaryTests(unittest.TestCase):
    def test_repeat_threshold_exact(self):
        b = CircuitBreaker(max_repeats=4)
        self.assertTrue(all(b.check("t", {"a": 1}).allowed for _ in range(3)))
        self.assertEqual(b.check("t", {"a": 1}).code, "repeat")
        self.assertEqual(CircuitBreaker(max_repeats=2).check("t").allowed, True)

    def test_blocked_call_not_recorded(self):
        b = CircuitBreaker()
        b.check("t"), b.check("t")
        before = list(b.history)
        self.assertFalse(b.check("t").allowed)
        self.assertEqual(b.history, before)

    def test_different_args_are_not_repeats(self):
        b = CircuitBreaker(max_cycle_len=1)  # isolate repeat logic
        self.assertTrue(all(b.check("t", {"page": i}).allowed for i in range(10)))

    def test_cycle_periods_3_and_4(self):
        for seq, block_at in [("ABCAB" + "C", 6), ("ABCDABC" + "D", 8)]:
            b = CircuitBreaker()
            results = [b.check(t).allowed for t in seq]
            self.assertEqual(results.index(False) + 1, block_at, seq)

    def test_period_beyond_max_cycle_len_not_detected(self):
        b = CircuitBreaker(max_cycle_len=2)
        self.assertTrue(all(b.check(t).allowed for t in "ABCABC"))

    def test_near_cycles_allowed(self):
        for seq in ["ABAC", "ABBA", "ABCBA"]:
            b = CircuitBreaker()
            self.assertTrue(all(b.check(t).allowed for t in seq), seq)

    def test_cycle_uses_args_not_just_tool_name(self):
        b = CircuitBreaker()
        calls = [("A", {"p": 1}), ("B", {}), ("A", {"p": 2}), ("B", {})]
        self.assertTrue(all(b.check(t, a).allowed for t, a in calls))

    def test_errors_one_below_threshold_allowed(self):
        b = CircuitBreaker(max_errors=3)
        b.record_result(False), b.record_result(False)
        self.assertTrue(b.check("t").allowed)
        b.record_result(False)
        self.assertEqual(b.check("u").code, "errors")

    def test_success_resets_error_streak_fully(self):
        b = CircuitBreaker(max_errors=2)
        b.record_result(False)
        b.record_result(True)
        b.record_result(False)
        self.assertEqual(b.consecutive_errors, 1)
        self.assertTrue(b.check("t").allowed)

    def test_budget_of_one_and_blocked_calls_do_not_consume_budget(self):
        b = CircuitBreaker(max_calls=1)
        self.assertTrue(b.check("a").allowed)
        self.assertEqual(b.check("b").code, "budget")
        b = CircuitBreaker(max_calls=3)
        b.check("x"), b.check("x"), b.check("x")  # third is a repeat block
        self.assertTrue(b.check("y").allowed)
        self.assertEqual(b.check("z").code, "budget")


class DlpEdgeTests(unittest.TestCase):
    def test_deep_nesting_and_non_strings(self):
        args = {"a": [{"b": ({"c": FAKE_OPENAI},)}], "n": 5, "f": None, "ok": True}
        out, found = redact_obj(args)
        self.assertNotIn(FAKE_OPENAI, str(out))
        self.assertEqual((out["n"], out["f"], out["ok"]), (5, None, True))
        self.assertEqual(found, ["openai_key"])

    def test_secret_in_dict_key_redacted(self):
        out, found = redact_obj({FAKE_GITHUB: "v"})
        self.assertNotIn(FAKE_GITHUB, str(out))
        self.assertEqual(found, ["github_token"])

    def test_multiple_secrets_in_one_string(self):
        out, found = redact(f"{FAKE_AWS} and {FAKE_AWS}")
        self.assertEqual(found, ["aws_access_key", "aws_access_key"])
        self.assertNotIn(FAKE_AWS, out)

    def test_guardrails_in_nested_args(self):
        self.assertEqual(check_args({"steps": [{"cmd": "rm -rf build"}, {"path": "../x"}]}),
                         ["destructive_command", "path_traversal"])

    def test_benign_text_not_flagged(self):
        benign = ["how to reboot a router", "shutdown hooks in Java", ".environment", "x.env.example",
                  "rm notes.txt", "format string", "range 1..10", "..hidden", "env file docs",
                  "the drop tables chart", "dd if=a.img of=b.img"]
        for s in benign:
            self.assertEqual(check_args({"q": s}), [], s)

    def test_commands_still_flagged(self):
        for s in ["sudo shutdown now", "ls; reboot", "DEL /S *", "format C:", "mkfs.ext4 /dev/sdb",
                  ":(){ :|:& };:", "drop database prod"]:
            self.assertIn("destructive_command", check_args({"cmd": s}), s)
        for s in [".env", "./.env", "C:\\app\\.env", "'.env.production'", "cat .env"]:
            self.assertIn("env_file_access", check_args({"p": s}), s)

    def test_known_false_positives(self):
        # Documented limitation: regexes can't tell prose from commands here.
        self.assertIn("destructive_command", check_args({"q": "I drop table tennis practice"}))
        self.assertIn("path_traversal", check_args({"q": "see ../README for details"}))


if __name__ == "__main__":
    unittest.main()

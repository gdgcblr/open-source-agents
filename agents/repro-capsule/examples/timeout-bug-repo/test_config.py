import unittest

from config import parse_timeout


class ParseTimeoutTests(unittest.TestCase):
    def test_explicit_zero_is_preserved(self):
        self.assertEqual(parse_timeout(0), 0)

    def test_missing_timeout_uses_default(self):
        self.assertEqual(parse_timeout(None), 30)


if __name__ == "__main__":
    unittest.main()

import unittest

from evaluation.run import run


class EvaluationSuiteTest(unittest.TestCase):
    def test_all_public_evaluation_cases_pass(self):
        report = run()

        self.assertEqual(11, report["total"])
        self.assertEqual(11, report["passed"])
        self.assertEqual(0, report["failed"])


if __name__ == "__main__":
    unittest.main()

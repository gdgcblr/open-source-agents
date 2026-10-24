import unittest

from evaluation.run import run


class EvaluationSuiteTest(unittest.TestCase):
    def test_all_public_evaluation_cases_pass(self):
        report = run()

        self.assertEqual(9, report["total"])
        self.assertEqual(9, report["passed"])
        self.assertEqual(0, report["failed"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Test Recommender."""

import unittest
from pathlib import Path
from blast_radius.java_analyzer import JavaAnalyzer
from blast_radius.test_recommender import TestRecommender
from blast_radius.models import JavaMethod, CallerReference

FIXTURE_REPO = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


class TestTestRecommender(unittest.TestCase):

    def setUp(self):
        self.analyzer = JavaAnalyzer(FIXTURE_REPO)
        self.recommender = TestRecommender(self.analyzer)

    def test_recommend_direct_test_caller(self):
        changed_method = JavaMethod(
            package_name="com.example.order",
            class_name="OrderService",
            method_name="validateOrder",
            signature="validateOrder(double)",
            return_type="void",
            modifiers=["public"],
            annotations=[],
            start_line=17,
            end_line=21,
            file_path="src/main/java/com/example/order/OrderService.java"
        )
        test_caller = CallerReference(
            caller_file="src/test/java/com/example/order/OrderServiceTest.java",
            caller_class="OrderServiceTest",
            caller_method="testValidateOrderInvalid",
            call_line=22,
            target_method_name="validateOrder",
            target_class_hint="orderService",
            code_snippet="orderService.validateOrder(0.5);",
            is_test=True
        )

        recs = self.recommender.recommend_tests([changed_method], [test_caller])
        self.assertTrue(len(recs) >= 1)
        high_rec = recs[0]
        self.assertEqual(high_rec.priority, "HIGH")
        self.assertEqual(high_rec.test_class, "OrderServiceTest")
        self.assertEqual(high_rec.test_method, "testValidateOrderInvalid")


if __name__ == "__main__":
    unittest.main()


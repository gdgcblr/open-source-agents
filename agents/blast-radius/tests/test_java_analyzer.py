"""Unit tests for Java source code parsing and caller discovery."""

import unittest
from pathlib import Path
from blast_radius.java_analyzer import JavaAnalyzer

FIXTURE_REPO = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


class TestJavaAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = JavaAnalyzer(FIXTURE_REPO)

    def test_find_all_java_files(self):
        files = self.analyzer.find_all_java_files()
        file_names = {f.name for f in files}
        self.assertIn("PaymentClient.java", file_names)
        self.assertIn("OrderService.java", file_names)
        self.assertIn("OrderController.java", file_names)
        self.assertIn("OrderServiceTest.java", file_names)

    def test_parse_payment_client_methods(self):
        payment_file = FIXTURE_REPO / "src" / "main" / "java" / "com" / "example" / "order" / "PaymentClient.java"
        methods = self.analyzer.parse_file(payment_file)
        method_names = {m.method_name for m in methods}

        self.assertIn("processPayment", method_names)
        self.assertIn("refundPayment", method_names)
        self.assertIn("getPaymentStatus", method_names)

        process_method = next(m for m in methods if m.method_name == "processPayment")
        self.assertEqual(process_method.class_name, "PaymentClient")
        self.assertEqual(process_method.return_type, "String")
        self.assertTrue(process_method.start_line < process_method.end_line)
        self.assertIn("public", process_method.modifiers)

    def test_find_direct_callers_for_process_payment(self):
        callers = self.analyzer.find_direct_callers("processPayment", "PaymentClient")
        self.assertTrue(len(callers) >= 1)

        caller_methods = {c.caller_method for c in callers}
        self.assertIn("createOrder", caller_methods)

        prod_caller = next(c for c in callers if c.caller_method == "createOrder")
        self.assertEqual(prod_caller.caller_class, "OrderService")
        self.assertFalse(prod_caller.is_test)

    def test_find_direct_callers_for_validate_order(self):
        callers = self.analyzer.find_direct_callers("validateOrder", "OrderService")
        caller_classes = {c.caller_class for c in callers}
        self.assertIn("OrderService", caller_classes)
        self.assertIn("OrderServiceTest", caller_classes)

        test_caller = next(c for c in callers if c.caller_class == "OrderServiceTest")
        self.assertTrue(test_caller.is_test)
        self.assertEqual(test_caller.caller_method, "testValidateOrderInvalid")

    def test_caching_performance(self):
        payment_file = FIXTURE_REPO / "src" / "main" / "java" / "com" / "example" / "order" / "PaymentClient.java"
        res1 = self.analyzer.parse_file(payment_file)
        res2 = self.analyzer.parse_file(payment_file)
        self.assertIs(res1, res2)  # Same cached instance in memory

    def test_multi_modifier_extraction(self):
        method_obj = self.analyzer._match_method(
            header_buffer="public static final synchronized String calculateHash(byte[] data) {",
            start_line=10,
            end_line=15,
            class_name="SecurityUtil",
            package_name="com.example.util",
            file_path="src/main/java/SecurityUtil.java",
            annotations=[]
        )
        self.assertIsNotNone(method_obj)
        self.assertIn("public", method_obj.modifiers)
        self.assertIn("static", method_obj.modifiers)
        self.assertIn("final", method_obj.modifiers)
        self.assertIn("synchronized", method_obj.modifiers)
        self.assertEqual(method_obj.return_type, "String")
        self.assertEqual(method_obj.method_name, "calculateHash")


if __name__ == "__main__":
    unittest.main()


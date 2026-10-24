"""Unit tests for Unified Diff Parser."""

import unittest
from blast_radius.diff_parser import DiffParser


class TestDiffParser(unittest.TestCase):

    def test_parse_simple_single_hunk(self):
        diff_text = """--- a/src/main/java/com/example/order/PaymentClient.java
+++ b/src/main/java/com/example/order/PaymentClient.java
@@ -8,4 +8,6 @@ public class PaymentClient {
         if (currency == null || currency.isBlank()) {
             throw new IllegalArgumentException("Currency must not be empty");
         }
+        // New validation check
+        if (amount > 10000.0) throw new IllegalArgumentException("Exceeds max limit");
         // Simulated HTTP payment gateway invocation
"""
        file_diffs = DiffParser.parse(diff_text)
        self.assertEqual(len(file_diffs), 1)
        fd = file_diffs[0]
        self.assertEqual(fd.old_path, "src/main/java/com/example/order/PaymentClient.java")
        self.assertEqual(fd.new_path, "src/main/java/com/example/order/PaymentClient.java")
        self.assertEqual(len(fd.hunks), 1)

        hunk = fd.hunks[0]
        self.assertEqual(hunk.new_start, 8)
        self.assertEqual(hunk.new_count, 6)
        # Lines 11 and 12 were added
        self.assertIn(11, hunk.modified_new_lines)
        self.assertIn(12, hunk.modified_new_lines)

    def test_parse_multi_file_diff(self):
        diff_text = """--- a/src/FileA.java
+++ b/src/FileA.java
@@ -10,2 +10,3 @@
+line10
--- a/src/FileB.java
+++ b/src/FileB.java
@@ -5,2 +5,3 @@
+line5
"""
        file_diffs = DiffParser.parse(diff_text)
        self.assertEqual(len(file_diffs), 2)
        self.assertEqual(file_diffs[0].new_path, "src/FileA.java")
        self.assertEqual(file_diffs[1].new_path, "src/FileB.java")

    def test_parse_deletion_only_hunk(self):
        diff_text = """--- a/src/OldService.java
+++ b/src/OldService.java
@@ -20,4 +20,1 @@
-lineToDelete1
-lineToDelete2
-lineToDelete3
"""
        file_diffs = DiffParser.parse(diff_text)
        self.assertEqual(len(file_diffs), 1)
        fd = file_diffs[0]
        self.assertTrue(len(fd.all_modified_lines) > 0)
        self.assertIn(20, fd.all_modified_lines)


if __name__ == "__main__":
    unittest.main()


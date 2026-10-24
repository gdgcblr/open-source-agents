"""Recommends impacted tests based on changed symbols and direct callers."""

from pathlib import Path
from typing import List, Dict, Set, Optional
from .models import JavaMethod, CallerReference, TestRecommendation
from .java_analyzer import JavaAnalyzer


class TestRecommender:
    """Identifies and ranks tests affected by code changes."""

    def __init__(self, analyzer: JavaAnalyzer):
        self.analyzer = analyzer

    def recommend_tests(
        self,
        changed_methods: List[JavaMethod],
        callers: List[CallerReference]
    ) -> List[TestRecommendation]:
        """Produces a ranked list of recommended test executions."""
        recommendations: List[TestRecommendation] = []
        seen_test_keys: Set[str] = set()

        changed_names = {m.method_name for m in changed_methods}
        changed_classes = {m.class_name for m in changed_methods}

        # 1. Direct callers that are tests (Priority: HIGH)
        for c in callers:
            if c.is_test and c.target_method_name in changed_names:
                key = f"{c.caller_file}::{c.caller_class}::{c.caller_method}"
                if key not in seen_test_keys:
                    seen_test_keys.add(key)
                    recommendations.append(TestRecommendation(
                        test_file=c.caller_file,
                        test_class=c.caller_class,
                        test_method=c.caller_method if c.caller_method != "TopLevel" else None,
                        priority="HIGH",
                        reason=f"Directly invokes changed method `{c.target_method_name}` at line {c.call_line}",
                        call_line=c.call_line
                    ))

        # 2. Tests that call intermediate production callers (Priority: HIGH/MEDIUM)
        prod_callers = [c for c in callers if not c.is_test]
        checked_prod_methods = set()
        for pc in prod_callers:
            method_key = (pc.caller_class, pc.caller_method)
            if method_key in checked_prod_methods:
                continue
            checked_prod_methods.add(method_key)

            # Look for tests that invoke this production caller
            secondary_callers = self.analyzer.find_direct_callers(pc.caller_method, pc.caller_class)
            for sc in secondary_callers:
                if sc.is_test:
                    key = f"{sc.caller_file}::{sc.caller_class}::{sc.caller_method}"
                    if key not in seen_test_keys:
                        seen_test_keys.add(key)
                        recommendations.append(TestRecommendation(
                            test_file=sc.caller_file,
                            test_class=sc.caller_class,
                            test_method=sc.caller_method if sc.caller_method != "TopLevel" else None,
                            priority="HIGH",
                            reason=f"Tests direct caller `{pc.caller_class}#{pc.caller_method}` (invoked at line {sc.call_line})",
                            call_line=sc.call_line
                        ))

        # 3. Conventional class test matching (e.g., PaymentClient -> PaymentClientTest)
        for java_file in self.analyzer.find_all_java_files():
            file_name = java_file.name
            rel_path = str(java_file.relative_to(self.analyzer.repo_root) if java_file.is_relative_to(self.analyzer.repo_root) else java_file)
            for changed_cls in changed_classes:
                if file_name in [f"{changed_cls}Test.java", f"{changed_cls}Tests.java", f"Test{changed_cls}.java"]:
                    key = f"{rel_path}::{changed_cls}Test"
                    if key not in seen_test_keys:
                        seen_test_keys.add(key)
                        recommendations.append(TestRecommendation(
                            test_file=rel_path,
                            test_class=changed_cls + "Test",
                            test_method=None,
                            priority="MEDIUM",
                            reason=f"Dedicated test suite for modified class `{changed_cls}`",
                            call_line=None
                        ))

        # Sort recommendations: HIGH first, then MEDIUM, then LOW
        priority_weights = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        recommendations.sort(key=lambda r: (priority_weights.get(r.priority, 9), r.test_file))
        return recommendations


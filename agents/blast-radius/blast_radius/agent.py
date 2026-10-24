"""BlastRadius Change Impact Analysis Agent."""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from .models import ImpactReport, JavaMethod, CallerReference, TestRecommendation
from .diff_parser import DiffParser
from .java_analyzer import JavaAnalyzer
from .test_recommender import TestRecommender
from .reporter import ImpactReporter


class BlastRadiusAgent:
    """Autonomous agent coordinating Git diff impact analysis on Java microservices."""

    STANDARD_LIMITATIONS = [
        "Polymorphic Dispatch: Invocations made via shared interfaces with multiple implementations are identified by method name; bytecode classpath resolution is required to disambiguate dynamic runtime implementations.",
        "Framework Reflection & Dependency Injection: Spring Bean autowiring (@Autowired, @Resource, @Inject), Spring events (ApplicationEventPublisher), and reflective calls are not tracked as direct lexical invocations.",
        "External Microservice Boundaries: Remote RPC, REST, and messaging consumers (Kafka, RabbitMQ) across external microservice repositories cannot be discovered from local source code alone.",
        "Target Scope: Analysis is bounded to Java source files (.java) in the specified repository root."
    ]

    def __init__(self, repo_path: str, api_key: Optional[str] = None, enable_llm: bool = False):
        self.repo_path = Path(repo_path).resolve()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.enable_llm = enable_llm or os.getenv("BLAST_RADIUS_ENABLE_LLM", "").lower() in ("1", "true", "yes")
        self.analyzer = JavaAnalyzer(self.repo_path)
        self.test_recommender = TestRecommender(self.analyzer)

    def analyze_diff(self, diff_content: str) -> ImpactReport:
        """Runs the full impact analysis workflow on a unified diff string."""
        if not self.repo_path.exists():
            raise FileNotFoundError(f"Target repository path does not exist: {self.repo_path}")

        # Step 1: Parse diff
        file_diffs = DiffParser.parse(diff_content)

        # Step 2: Identify changed Java methods
        changed_methods: List[JavaMethod] = []
        for fd in file_diffs:
            if fd.new_path.endswith(".java") or fd.old_path.endswith(".java"):
                target_path = fd.new_path or fd.old_path
                methods = self.analyzer.find_methods_in_diff(target_path, fd.all_modified_lines)
                changed_methods.extend(methods)

        # Deduplicate changed methods
        unique_methods = []
        seen_methods = set()
        for m in changed_methods:
            key = (m.file_path, m.class_name, m.method_name, m.start_line)
            if key not in seen_methods:
                seen_methods.add(key)
                unique_methods.append(m)
        changed_methods = unique_methods

        # Step 3: Discover direct callers
        all_callers: List[CallerReference] = []
        for m in changed_methods:
            callers = self.analyzer.find_direct_callers(m.method_name, m.class_name)
            all_callers.extend(callers)

        # Deduplicate callers
        unique_callers = []
        seen_callers = set()
        for c in all_callers:
            key = (c.caller_file, c.caller_class, c.caller_method, c.call_line, c.target_method_name)
            if key not in seen_callers:
                seen_callers.add(key)
                unique_callers.append(c)
        all_callers = unique_callers

        # Step 4: Recommend tests
        recommended_tests = self.test_recommender.recommend_tests(changed_methods, all_callers)

        # Step 5: Identify uncovered changed methods
        covered_method_names = {c.target_method_name for c in all_callers if c.is_test}
        # Also check if a test suite covers the class using prefix/suffix stripping
        covered_classes = set()
        for t in recommended_tests:
            c_name = t.test_class
            if c_name.startswith("Test"):
                c_name = c_name.removeprefix("Test")
            if c_name.endswith("Tests"):
                c_name = c_name.removesuffix("Tests")
            elif c_name.endswith("Test"):
                c_name = c_name.removesuffix("Test")
            covered_classes.add(c_name)

        uncovered_methods = []
        for m in changed_methods:
            if m.method_name not in covered_method_names and m.class_name not in covered_classes:
                uncovered_methods.append(m)

        # Step 6: Formulate Report
        report = ImpactReport(
            target_repo=str(self.repo_path),
            diff_file_count=len(file_diffs),
            changed_methods=changed_methods,
            callers=all_callers,
            recommended_tests=recommended_tests,
            uncovered_methods=uncovered_methods,
            limitations=list(self.STANDARD_LIMITATIONS),
            summary_notes=[]
        )

        # Step 7: Risk assessment
        report.risk = ImpactReporter.evaluate_risk(report)

        # Step 8: Optional LLM Reasoning enrichment (requires explicit opt-in)
        if self.enable_llm and self.api_key:
            self._enrich_with_llm(report, diff_content)

        return report

    def _enrich_with_llm(self, report: ImpactReport, diff_content: str) -> None:
        """Enriches the report with semantic risk insights using Gemini API.

        Only called when both enable_llm=True and a valid API key are present.
        Sends method signatures, caller names, and up to 2KB of diff content
        to the Gemini API for semantic risk analysis.
        """
        if not self.api_key:
            return

        import json
        import urllib.request

        model = os.getenv("MODEL_NAME", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        prompt = (
            "You are BlastRadius, a Java change impact analysis agent. "
            "Analyze the following Git diff and impacted callers. "
            "Provide 1-2 concise bullet points highlighting semantic risks (e.g. edge case handling, nullability, breaking contract changes).\n\n"
            f"Changed Methods: {[m.signature for m in report.changed_methods]}\n"
            f"Callers: {[f'{c.caller_class}#{c.caller_method}' for c in report.callers]}\n"
            f"Diff snippet:\n{diff_content[:2000]}"
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ]
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key
                }
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        llm_text = parts[0].get("text", "").strip()
                        report.summary_notes.append(f"Gemini Semantic Analysis:\n{llm_text}")
        except Exception as e:
            report.summary_notes.append(
                f"Note: LLM enrichment attempted but unavailable ({type(e).__name__}). Using deterministic analysis."
            )


"""Run the real test suite and write a reproducible machine-readable report."""
from collections import defaultdict
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import unittest

from .config import PROJECT_ROOT


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def startTest(self, test):
        super().startTest(test)
        self.cases.append({"id": test.id(), "metric": getattr(getattr(test, test._testMethodName), "metric", "regression_and_safety"), "status": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.cases[-1].update(status="failed", detail=self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.cases[-1].update(status="failed", detail=self._exc_info_to_string(err, test))

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.cases[-1].update(status="failed", detail=self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.cases[-1].update(status="skipped", detail=reason)


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(suite)
    metrics = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
    for case in result.cases:
        metrics[case["metric"]]["total"] += 1
        metrics[case["metric"]][case["status"]] += 1
    packages = {}
    for name in ("google-adk", "python-dotenv"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    output = {"suite": "TraceGuard AI offline golden and regression evaluations", "python": platform.python_version(),
              "platform": platform.system(), "dependencies": packages, "fixture_date": "2026-10-24",
              "total": result.testsRun, "passed": sum(c["status"] == "passed" for c in result.cases),
              "failed": sum(c["status"] == "failed" for c in result.cases), "skipped": len(result.skipped),
              "metrics": dict(metrics), "cases": result.cases,
              "coverage_limitations": ["Synthetic fixtures; no production incident ground truth.",
                  "Curated advisory subset; no guarantee of complete vulnerability coverage.",
                  "ADK integration uses a fake model and real tools/runner; it is not a live Gemini evaluation.",
                  "Redaction and incident indicators are heuristics, not complete DLP or intrusion detection.",
                  "Only Windows/Python 3.12 tested; Linux, macOS, and Docker are untested."]}
    path = Path(os.getenv("TRIAGE_EVAL_REPORT", str(PROJECT_ROOT / "evaluations/report.json")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"{output['passed']}/{output['total']} passed; {output['failed']} failed; {output['skipped']} skipped.")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

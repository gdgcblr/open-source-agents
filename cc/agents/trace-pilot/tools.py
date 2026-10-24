import re
import json
from typing import Dict, List, Any

class LogAnalyzerTool:
    """Parses raw error logs and tracebacks to extract error classes, stack frames, and evidence line numbers."""

    @staticmethod
    def run(log_content: str) -> Dict[str, Any]:
        lines = log_content.splitlines()
        errors = []
        stack_frames = []
        evidence_lines = []

        error_pattern = re.compile(r'(?:Error|Exception|Failed|CRITICAL|Traceback|AssertionError):\s*(.*)', re.IGNORECASE)
        file_path_pattern = re.compile(r'File "([^"]+)", line (\d+), in (.+)')

        for idx, line in enumerate(lines, start=1):
            # Check for error matches
            err_match = error_pattern.search(line)
            if err_match:
                errors.append({
                    "line_number": idx,
                    "content": line.strip(),
                    "message": err_match.group(1)
                })
                evidence_lines.append(idx)

            # Check for stack frames
            frame_match = file_path_pattern.search(line)
            if frame_match:
                stack_frames.append({
                    "line_number": idx,
                    "file": frame_match.group(1),
                    "line": frame_match.group(2),
                    "function": frame_match.group(3),
                    "content": line.strip()
                })
                evidence_lines.append(idx)

        return {
            "total_lines_analyzed": len(lines),
            "errors_detected": errors,
            "stack_frames": stack_frames,
            "evidence_line_numbers": sorted(list(set(evidence_lines)))
        }

class TestInspectorTool:
    """Parses test execution output (e.g., pytest results) to isolate failing tests and failure assertions."""

    @staticmethod
    def run(test_output: str) -> Dict[str, Any]:
        lines = test_output.splitlines()
        failing_tests = []
        summary = {"passed": 0, "failed": 0, "errors": 0, "total": 0}

        fail_test_pattern = re.compile(r'FAILED\s+([^\s]+)')
        summary_pattern = re.compile(r'==+\s*(?:(\d+)\s+failed)?(?:,\s*)?(?:(\d+)\s+passed)?(?:,\s*)?(?:(\d+)\s+error)?.*?==+')

        for idx, line in enumerate(lines, start=1):
            f_match = fail_test_pattern.search(line)
            if f_match:
                failing_tests.append({
                    "test_name": f_match.group(1),
                    "line_number": idx,
                    "output_line": line.strip()
                })

            s_match = summary_pattern.search(line)
            if s_match:
                failed_str, passed_str, error_str = s_match.groups()
                if failed_str: summary["failed"] = int(failed_str)
                if passed_str: summary["passed"] = int(passed_str)
                if error_str: summary["errors"] = int(error_str)
                summary["total"] = summary["failed"] + summary["passed"] + summary["errors"]

        return {
            "failing_tests": failing_tests,
            "test_summary": summary,
            "total_failures": len(failing_tests)
        }

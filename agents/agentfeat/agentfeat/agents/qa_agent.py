"""QA Spoke Agent: Code review, AST validation, security checks, and isolated test execution."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from agentfeat.agents.base_agent import BaseAgent
from agentfeat.core.validator import CodeValidator
from agentfeat.models.schemas import FileChange
from agentfeat.orchestration.messages import AgentMessage
from agentfeat.utils.file_ops import apply_file_changes


class QAAgent(BaseAgent):
    """Spoke agent responsible for code validation, quality gates, and genuine test execution."""

    def __init__(self) -> None:
        super().__init__(name="qa", role="Testing, Syntax Verification & Security Gate")

    def process(self, message: AgentMessage) -> AgentMessage:
        changes_data = message.payload.get("changes", [])
        target_dir_str = message.payload.get("target_dir", ".")

        if not changes_data:
            return AgentMessage.create_response(
                message,
                sender=self.name,
                payload={
                    "passed": True,
                    "validated_changes": [],
                    "findings": ["No file changes provided for review."],
                    "test_coverage_detected": False,
                    "test_execution_passed": False,
                },
            )

        target_dir = Path(target_dir_str).resolve()
        changes: List[FileChange] = [FileChange.model_validate(c) for c in changes_data]

        findings: List[str] = []
        # Phase 1: Static AST, Syntax, Secret, and Path Traversal Validation
        all_passed = CodeValidator.validate_all(changes, target_root=target_dir)

        test_files_found: List[str] = []
        for c in changes:
            if not c.is_valid:
                findings.append(f"Validation failure in {c.file_path}: {c.validation_error}")
            if "test" in c.file_path.lower() and c.file_path.endswith(".py"):
                test_files_found.append(c.file_path)

        if not test_files_found:
            findings.append("Warning: No automated test file was detected in proposed changes.")
        else:
            findings.append(f"Detected {len(test_files_found)} test file(s): {', '.join(test_files_found)}")

        if all_passed:
            findings.append("Static Analysis: AST syntax checks and security boundary verifications passed.")

        # Phase 2: Isolated Dynamic Test Execution
        test_execution_passed = False
        if all_passed and test_files_found and target_dir.is_dir():
            test_passed, test_output, exit_code = self._run_isolated_tests(target_dir, changes)
            if test_passed:
                test_execution_passed = True
                findings.append(f"Dynamic QA Gate PASSED: Functional pytest execution succeeded (exit code {exit_code}).")
                findings.append(f"Test Summary: {test_output.strip().splitlines()[-1] if test_output.strip() else 'All tests passed'}")
            else:
                all_passed = False
                test_execution_passed = False
                findings.append(f"Dynamic QA Gate FAILED: Test execution exited with code {exit_code}.")
                # Capture the failure lines
                tail_lines = [line for line in test_output.splitlines() if line.strip()][-4:]
                findings.append(f"Test Error Details: {' | '.join(tail_lines)}")

        return AgentMessage.create_response(
            message,
            sender=self.name,
            payload={
                "passed": all_passed,
                "validated_changes": [c.model_dump() for c in changes],
                "findings": findings,
                "test_coverage_detected": len(test_files_found) > 0,
                "test_execution_passed": test_execution_passed,
            },
        )

    def _run_isolated_tests(self, target_dir: Path, changes: List[FileChange]) -> tuple:
        """Execute generated tests in an isolated temporary directory clone without touching target_dir."""
        ignore_dirs = {
            ".git", ".venv", "venv", "__pycache__", "node_modules",
            ".agentfeat_backup", ".pytest_cache"
        }

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_path = Path(temp_dir_str)

            # Copy existing workspace files to sandbox
            for item in target_dir.iterdir():
                if item.name in ignore_dirs or item.name.startswith("."):
                    continue
                dst = temp_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, ignore=shutil.ignore_patterns(*ignore_dirs))
                elif item.is_file():
                    shutil.copy2(item, dst)

            # Apply proposed changes into sandbox
            apply_file_changes(temp_path, changes, create_backups=False)

            # Run pytest in the sandbox
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                "-v",
                "--tb=short",
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(temp_path),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
                return proc.returncode == 0, output, proc.returncode
            except subprocess.TimeoutExpired:
                return False, "Test execution timed out after 15 seconds", -1
            except Exception as e:
                return False, f"Failed to execute test runner: {str(e)}", -1

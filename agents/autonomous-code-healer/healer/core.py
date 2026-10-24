"""Enterprise Autonomous Code Healer Reasoning Engine and Transaction Manager."""

import datetime
import difflib
import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from .ast_guard import validate_code_safety
from .sandbox import run_sandboxed_command
from .mock_healer import MockHealerEngine

logger = logging.getLogger(__name__)

HEALER_SYSTEM_PROMPT = """You are the Senior Autonomous Software Engineer and Code Healer Agent.
A test suite or execution command is failing for the target file.
Your objective is to diagnose the root cause from the error traceback and provide the complete, corrected code.

Rules:
1. Provide the COMPLETE file content with the bug surgically fixed.
2. Ensure valid Python syntax.
3. Do not include extraneous markdown commentary outside of the code block.
4. Enclose the fixed code in ```python ... ``` fences.
"""


class HealingAttempt(BaseModel):
    """Audit record for a single healing cycle attempt."""
    attempt_num: int
    ast_safe: bool
    ast_reason: str
    test_passed: bool
    exit_code: int
    duration_seconds: float
    error_snippet: str = ""


class HealingMetrics(BaseModel):
    """Operational telemetry and audit metrics for the healing process."""
    run_id: str
    target_file: str
    test_command: str
    started_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None
    duration_seconds: float = 0.0
    attempts_made: int = 0
    final_status: str
    diff_lines_changed: int = 0
    mock_mode: bool = False


class AutonomousCodeHealer:
    """Autonomous coding agent with AST validation, sandboxed execution, and atomic rollback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        max_attempts: int = 3,
        sandbox_timeout: int = 10,
        auto_rollback: bool = True,
        mock_mode: bool = False,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.max_attempts = max(1, min(int(max_attempts or 3), 6))
        self.sandbox_timeout = max(2, min(int(sandbox_timeout or 10), 60))
        self.auto_rollback = auto_rollback
        self.event_callback = event_callback

        if mock_mode or not self.api_key or self.api_key == "your_gemini_api_key_here":
            self.mock_mode = True
            self.mock_engine = MockHealerEngine()
            self.client = None
            logger.info("AutonomousCodeHealer initialized in OFFLINE MOCK MODE.")
        else:
            self.mock_mode = False
            self.mock_engine = None
            self.client = self._init_gemini_client()
            logger.info(f"AutonomousCodeHealer connected to live Gemini model: {self.model_name}")

    def _init_gemini_client(self):
        """Initializes Google GenAI client."""
        try:
            from google import genai
            return genai.Client(api_key=self.api_key)
        except ImportError:
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=self.api_key)
                return legacy_genai.GenerativeModel(self.model_name)
            except ImportError:
                logger.warning("Google GenAI SDKs unavailable. Switching to mock engine.")
                self.mock_mode = True
                self.mock_engine = MockHealerEngine()
                return None

    def _dispatch_event(self, event_type: str, message: str, payload: Optional[Any] = None):
        """Dispatches progress notifications to listener."""
        if self.event_callback:
            try:
                self.event_callback({
                    "event": event_type,
                    "message": message,
                    "payload": payload,
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
                })
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    def _call_llm_fix(self, file_path: str, code: str, failure_log: str) -> str:
        """Prompts LLM or Mock engine for a corrected version of the code."""
        if self.mock_mode or not self.client:
            return self.mock_engine.heal_code(file_path, code, failure_log)

        prompt = (
            f"{HEALER_SYSTEM_PROMPT}\n\n"
            f"Target File: {file_path}\n\n"
            f"Current Code:\n```python\n{code}\n```\n\n"
            f"Test / Execution Failure:\n```\n{failure_log}\n```\n\n"
            "Provide the complete corrected code inside ```python ... ```:"
        )

        try:
            if hasattr(self.client, "models"):
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                text = resp.text
            else:
                resp = self.client.generate_content(prompt)
                text = resp.text

            # Extract python block
            match = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                return match.group(1).strip()
            return text.strip()
        except Exception as e:
            logger.error(f"Live LLM call error: {e}. Falling back to mock engine.")
            return self.mock_engine.heal_code(file_path, code, failure_log)

    def heal(self, file_path: str, test_command: str) -> Dict[str, Any]:
        """Autonomously diagnoses, patches, verifies, and potentially rolls back code.

        Args:
            file_path: Path to the target source code file.
            test_command: Verification command (e.g. 'pytest test_math.py').

        Returns:
            Dictionary containing final status, diff, attempts log, and metrics.
        """
        abs_target = os.path.abspath(file_path)
        if not os.path.exists(abs_target) or not os.path.isfile(abs_target):
            raise FileNotFoundError(f"Target file not found: {file_path}")

        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.datetime.now()
        start_perf = time.perf_counter()
        target_dir = os.path.dirname(abs_target)

        # 1. Atomic Backup
        with open(abs_target, "r", encoding="utf-8") as f:
            original_code = f.read()

        logger.info(f"[{run_id}] Starting code healing on '{abs_target}'")
        self._dispatch_event("start", f"Backed up {os.path.basename(abs_target)} ({len(original_code)} chars).")

        # 2. Run Baseline Test
        self._dispatch_event("test_baseline", f"Running baseline verification: '{test_command}'")
        baseline = run_sandboxed_command(test_command, cwd=target_dir, timeout=self.sandbox_timeout)

        if baseline["passed"]:
            logger.info(f"[{run_id}] Baseline tests already pass. No healing required.")
            self._dispatch_event("success", "Target code already passes all tests. Zero patches needed.")
            duration = round(time.perf_counter() - start_perf, 2)
            metrics = HealingMetrics(
                run_id=run_id,
                target_file=abs_target,
                test_command=test_command,
                started_at=started_at,
                completed_at=datetime.datetime.now(),
                duration_seconds=duration,
                attempts_made=0,
                final_status="already_passing",
                diff_lines_changed=0,
                mock_mode=self.mock_mode
            )
            return {
                "status": "already_passing",
                "file_path": abs_target,
                "original_code": original_code,
                "healed_code": original_code,
                "diff": "",
                "attempts": [],
                "metrics": metrics.model_dump()
            }

        # 3. Recursive Healing Loop
        attempts: List[HealingAttempt] = []
        current_code = original_code
        last_failure = baseline["stderr"] or baseline["stdout"] or f"Exit code {baseline['exit_code']}"
        success = False

        for attempt_idx in range(1, self.max_attempts + 1):
            attempt_start = time.perf_counter()
            self._dispatch_event("attempt_start", f"Cycle {attempt_idx}/{self.max_attempts}: Analyzing failure traceback.")

            # Propose Fix
            proposed_fix = self._call_llm_fix(abs_target, current_code, last_failure)

            # AST Safety Guardrail
            is_safe, ast_reason = validate_code_safety(proposed_fix)
            if not is_safe:
                logger.warning(f"[{run_id}] Attempt {attempt_idx} rejected by AST Guard: {ast_reason}")
                self._dispatch_event("ast_rejected", f"Attempt {attempt_idx} rejected: {ast_reason}")
                attempts.append(HealingAttempt(
                    attempt_num=attempt_idx,
                    ast_safe=False,
                    ast_reason=ast_reason,
                    test_passed=False,
                    exit_code=-1,
                    duration_seconds=round(time.perf_counter() - attempt_start, 2),
                    error_snippet=ast_reason
                ))
                continue

            # Write patch atomically
            with open(abs_target, "w", encoding="utf-8") as f:
                f.write(proposed_fix)

            # Re-run test in sandbox
            self._dispatch_event("test_run", f"Cycle {attempt_idx}: Re-testing patch with '{test_command}'")
            retest = run_sandboxed_command(test_command, cwd=target_dir, timeout=self.sandbox_timeout)
            attempt_dur = round(time.perf_counter() - attempt_start, 2)

            if retest["passed"]:
                logger.info(f"[{run_id}] Patch verified and PASSED on attempt {attempt_idx}!")
                self._dispatch_event("success", f"Patch verified on attempt {attempt_idx}! All tests green.")
                attempts.append(HealingAttempt(
                    attempt_num=attempt_idx,
                    ast_safe=True,
                    ast_reason="Passed AST check",
                    test_passed=True,
                    exit_code=0,
                    duration_seconds=attempt_dur,
                    error_snippet=""
                ))
                current_code = proposed_fix
                success = True
                break
            else:
                last_failure = retest["stderr"] or retest["stdout"] or f"Exit code {retest['exit_code']}"
                logger.info(f"[{run_id}] Attempt {attempt_idx} failed tests. Retrying...")
                self._dispatch_event("attempt_failed", f"Cycle {attempt_idx} tests failed: {last_failure[:150]}...")
                attempts.append(HealingAttempt(
                    attempt_num=attempt_idx,
                    ast_safe=True,
                    ast_reason="Passed AST check",
                    test_passed=False,
                    exit_code=retest["exit_code"],
                    duration_seconds=attempt_dur,
                    error_snippet=last_failure[:300]
                ))
                current_code = proposed_fix

        # 4. Atomic Rollback Check if Unsuccessful
        if not success:
            if self.auto_rollback:
                logger.warning(f"[{run_id}] Max attempts ({self.max_attempts}) reached without fix. Rolling back file.")
                self._dispatch_event("rollback", f"Max attempts exhausted. Reverting {os.path.basename(abs_target)} to original.")
                with open(abs_target, "w", encoding="utf-8") as f:
                    f.write(original_code)
                final_code = original_code
                final_status = "rollback_after_failed_attempts"
            else:
                final_code = current_code
                final_status = "failed_unverified"
        else:
            final_code = current_code
            final_status = "healed_successfully"

        # Generate Unified Diff
        diff_lines = list(difflib.unified_diff(
            original_code.splitlines(keepends=True),
            final_code.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(abs_target)}",
            tofile=f"b/{os.path.basename(abs_target)}"
        ))
        diff_text = "".join(diff_lines)

        duration = round(time.perf_counter() - start_perf, 2)
        metrics = HealingMetrics(
            run_id=run_id,
            target_file=abs_target,
            test_command=test_command,
            started_at=started_at,
            completed_at=datetime.datetime.now(),
            duration_seconds=duration,
            attempts_made=len(attempts),
            final_status=final_status,
            diff_lines_changed=len(diff_lines),
            mock_mode=self.mock_mode
        )

        return {
            "status": final_status,
            "file_path": abs_target,
            "original_code": original_code,
            "healed_code": final_code,
            "diff": diff_text,
            "attempts": [a.model_dump() for a in attempts],
            "metrics": metrics.model_dump()
        }

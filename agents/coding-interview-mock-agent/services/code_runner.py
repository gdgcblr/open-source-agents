"""
Code Execution Service for Coding Interview Mock Agent.

Provides a secure execution layer for candidate code submissions.
For MVP: Uses subprocess with strict timeouts and resource bounds.

=============================================================================
TODO: Docker Sandbox Migration
In production, migrate this subprocess execution to an isolated, unprivileged
Docker container runner (e.g., using docker-py or gVisor / runsc container runtime)
with the following safeguards:
  1. Network disabled: --network none
  2. Memory capped: --memory 128m
  3. CPU throttled: --cpus 0.5
  4. Read-only root filesystem: --read-only
  5. Dropped Linux capabilities and non-root user (UID 1000)
  6. ephemeral tmpfs for execution artifacts
=============================================================================
"""

from __future__ import annotations
import os
import sys
import shutil
import tempfile
import time
import subprocess
from typing import Optional, Dict, Any, Union
from models.schemas import ProgrammingLanguage, RunCodeResponse


DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_OUTPUT_BYTES = 50 * 1024  # 50 KB output limit to prevent stdout flooding


class CodeExecutionService:
    """
    Executes candidate code in supported languages (Python, JavaScript, C++, Java)
    using isolated temporary processes with timeouts and output capture.
    """

    def __init__(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds

    def execute(
        self,
        code: str,
        language: Union[ProgrammingLanguage, str] = ProgrammingLanguage.PYTHON,
        stdin_input: Optional[str] = ""
    ) -> RunCodeResponse:
        """
        Execute arbitrary candidate code with timeout and error capturing.
        """
        lang = language if isinstance(language, ProgrammingLanguage) else ProgrammingLanguage(language.lower())

        start_time = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="mock_agent_exec_") as temp_dir:
            try:
                if lang == ProgrammingLanguage.PYTHON:
                    return self._execute_python(code, temp_dir, stdin_input, start_time)
                elif lang == ProgrammingLanguage.JAVASCRIPT:
                    return self._execute_javascript(code, temp_dir, stdin_input, start_time)
                elif lang == ProgrammingLanguage.CPP:
                    return self._execute_cpp(code, temp_dir, stdin_input, start_time)
                elif lang == ProgrammingLanguage.JAVA:
                    return self._execute_java(code, temp_dir, stdin_input, start_time)
                else:
                    return RunCodeResponse(
                        stdout="",
                        stderr=f"Unsupported language: {lang}",
                        exit_code=1,
                        execution_time_ms=0.0,
                        success=False,
                        details="Unsupported language runtime."
                    )
            except subprocess.TimeoutExpired:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return RunCodeResponse(
                    stdout="",
                    stderr=f"TimeLimitExceeded: Process exceeded maximum execution time of {self.timeout_seconds} seconds.",
                    exit_code=-1,
                    execution_time_ms=round(elapsed_ms, 2),
                    success=False,
                    details="Execution timed out. Please check for infinite loops or non-terminating recursion."
                )
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return RunCodeResponse(
                    stdout="",
                    stderr=f"ExecutionError: {str(e)}",
                    exit_code=1,
                    execution_time_ms=round(elapsed_ms, 2),
                    success=False,
                    details="An unexpected error occurred during execution."
                )

    def _execute_python(self, code: str, temp_dir: str, stdin_input: Optional[str], start_time: float) -> RunCodeResponse:
        script_path = os.path.join(temp_dir, "solution.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Detect suitable python binary
        py_bin = sys.executable if sys.executable and os.path.exists(sys.executable) else shutil.which("python") or shutil.which("python3")
        if not py_bin:
            return RunCodeResponse(
                stdout="",
                stderr="Python interpreter executable not found in system PATH.",
                exit_code=127,
                execution_time_ms=0.0,
                success=False,
                details="Environment missing Python runtime."
            )

        cmd = [py_bin, "-u", script_path]
        return self._run_process(cmd, temp_dir, stdin_input, start_time)

    def _execute_javascript(self, code: str, temp_dir: str, stdin_input: Optional[str], start_time: float) -> RunCodeResponse:
        node_bin = shutil.which("node")
        if not node_bin:
            return RunCodeResponse(
                stdout="",
                stderr="Node.js runtime ('node') not found in system PATH. Please install Node.js to execute JavaScript code.",
                exit_code=127,
                execution_time_ms=0.0,
                success=False,
                details="Environment missing Node.js runtime."
            )

        script_path = os.path.join(temp_dir, "solution.js")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        cmd = [node_bin, script_path]
        return self._run_process(cmd, temp_dir, stdin_input, start_time)

    def _execute_cpp(self, code: str, temp_dir: str, stdin_input: Optional[str], start_time: float) -> RunCodeResponse:
        compiler_bin = shutil.which("g++") or shutil.which("clang++")
        if not compiler_bin:
            return RunCodeResponse(
                stdout="",
                stderr="C++ compiler ('g++' or 'clang++') not found in system PATH. Please install MinGW or GCC.",
                exit_code=127,
                execution_time_ms=0.0,
                success=False,
                details="Environment missing C++ compiler."
            )

        src_path = os.path.join(temp_dir, "solution.cpp")
        exe_name = "solution.exe" if os.name == "nt" else "solution"
        exe_path = os.path.join(temp_dir, exe_name)

        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Compile step
        compile_cmd = [compiler_bin, "-O2", "-std=c++17", src_path, "-o", exe_path]
        compile_proc = subprocess.run(
            compile_cmd,
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0
        )

        if compile_proc.returncode != 0:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return RunCodeResponse(
                stdout="",
                stderr=f"Compilation Error:\n{compile_proc.stderr}",
                exit_code=compile_proc.returncode,
                execution_time_ms=round(elapsed_ms, 2),
                success=False,
                details="C++ compilation failed."
            )

        cmd = [exe_path]
        return self._run_process(cmd, temp_dir, stdin_input, start_time)

    def _execute_java(self, code: str, temp_dir: str, stdin_input: Optional[str], start_time: float) -> RunCodeResponse:
        javac_bin = shutil.which("javac")
        java_bin = shutil.which("java")
        if not javac_bin or not java_bin:
            return RunCodeResponse(
                stdout="",
                stderr="Java JDK ('javac' / 'java') not found in system PATH. Please install JDK 17+.",
                exit_code=127,
                execution_time_ms=0.0,
                success=False,
                details="Environment missing Java runtime."
            )

        src_path = os.path.join(temp_dir, "Solution.java")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Compile step
        compile_proc = subprocess.run(
            [javac_bin, src_path],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0
        )

        if compile_proc.returncode != 0:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return RunCodeResponse(
                stdout="",
                stderr=f"Java Compilation Error:\n{compile_proc.stderr}",
                exit_code=compile_proc.returncode,
                execution_time_ms=round(elapsed_ms, 2),
                success=False,
                details="Java compilation failed."
            )

        cmd = [java_bin, "Solution"]
        return self._run_process(cmd, temp_dir, stdin_input, start_time)

    def _run_process(
        self,
        cmd: list,
        cwd: str,
        stdin_input: Optional[str],
        start_time: float
    ) -> RunCodeResponse:
        """Helper to run command and capture output safely."""
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=stdin_input or "",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout_seconds
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Truncate overly verbose output if needed
        stdout = proc.stdout[:MAX_OUTPUT_BYTES]
        stderr = proc.stderr[:MAX_OUTPUT_BYTES]

        return RunCodeResponse(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            execution_time_ms=round(elapsed_ms, 2),
            success=(proc.returncode == 0),
            details="Execution succeeded." if proc.returncode == 0 else "Execution failed with non-zero exit code."
        )


# Singleton instance for application use
code_runner = CodeExecutionService()


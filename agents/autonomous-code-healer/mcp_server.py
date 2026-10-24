"""FastMCP Server exposing Autonomous Code Healer tools to IDEs and LLMs."""

import json
import os
import sys
from typing import Any, Dict

# Safe UTF-8 reconfiguration on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from healer.ast_guard import validate_code_safety
from healer.core import AutonomousCodeHealer
from healer.sandbox import run_sandboxed_command


def create_mcp_server():
    """Constructs and registers tools on the FastMCP instance."""
    if FastMCP is None:
        return None

    mcp = FastMCP(
        "Autonomous Code Healer",
        instructions="Autonomous test-driven bug-fixing and refactoring agent with static AST guardrails and atomic rollback.",
    )

    @mcp.tool()
    def heal_code(
        file_path: str,
        test_command: str = "pytest",
        max_attempts: int = 3,
        auto_rollback: bool = True,
    ) -> str:
        """Autonomously diagnoses test failures, patches code, verifies in sandbox, and produces diff.

        Args:
            file_path: Absolute or relative path to the Python source file.
            test_command: Verification command (e.g. 'pytest test_math.py').
            max_attempts: Maximum healing cycles before rolling back (1-5).
            auto_rollback: Whether to restore original code if all cycles fail.

        Returns:
            JSON string containing final status, diff, attempt details, and metrics.
        """
        healer = AutonomousCodeHealer(
            max_attempts=max_attempts,
            auto_rollback=auto_rollback,
        )
        result = healer.heal(file_path=file_path, test_command=test_command)
        return json.dumps(
            {
                "status": result["status"],
                "file_path": result["file_path"],
                "diff": result["diff"],
                "attempts": result["attempts"],
                "metrics": result["metrics"],
            },
            indent=2,
            default=str,
        )

    @mcp.tool()
    def audit_ast_safety(code: str) -> str:
        """Statically inspects Python code using AST to verify syntax and ensure no dangerous calls.

        Args:
            code: Python source code string.

        Returns:
            JSON string with 'is_safe' boolean and 'reason' explanation.
        """
        is_safe, reason = validate_code_safety(code)
        return json.dumps({"is_safe": is_safe, "reason": reason}, indent=2)

    @mcp.tool()
    def run_sandboxed_command_tool(command: str, timeout: int = 10) -> str:
        """Executes a verification command inside a sandboxed subprocess with hard timeout.

        Args:
            command: Shell or python command to execute.
            timeout: Maximum seconds before process termination.

        Returns:
            JSON string with exit_code, stdout, stderr, and passed boolean.
        """
        res = run_sandboxed_command(command, timeout=timeout)
        return json.dumps(res, indent=2)

    return mcp


mcp_server = create_mcp_server()


def main():
    if "--test" in sys.argv:
        print("[MCP] Running Autonomous Code Healer FastMCP self-test...")
        if mcp_server is None:
            print("[MCP ERROR] FastMCP is not installed in the environment.")
            sys.exit(1)

        # Test AST audit
        safe_code = "def add(x, y): return x + y"
        unsafe_code = "import os\nos.system('calc.exe')"
        safe_res, _ = validate_code_safety(safe_code)
        unsafe_res, reason = validate_code_safety(unsafe_code)
        assert safe_res is True, "Safe code should pass AST check"
        assert unsafe_res is False, f"Unsafe code should be blocked: {reason}"

        print(f"[MCP SUCCESS] FastMCP initialized successfully: {mcp_server.name}")
        print(f"[MCP SUCCESS] AST Guard tool verified (blocked: {reason})")
        sys.exit(0)

    if mcp_server:
        mcp_server.run()
    else:
        print("MCP SDK not installed. Run `pip install mcp`.")
        sys.exit(1)


if __name__ == "__main__":
    main()

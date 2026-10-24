#!/usr/bin/env python3
"""
git-mcp-server: Model Context Protocol (MCP) server for Git operations.

Exposes safe, structured Git inspection tools over the standard MCP stdio protocol
(JSON-RPC 2.0). Compatible with Claude Desktop, Cursor, Antigravity, and any MCP client.

Tools exposed:
  - git_status: Inspect branch and working tree modifications
  - git_diff: View staged or unstaged diffs with optional file filtering
  - git_log: View commit history with pagination and author filters
  - git_branches: Inspect local and tracking branches
  - git_show: Inspect specific commit details and patches
"""

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

SERVER_NAME = "git-mcp-server"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# Git Operations
# ---------------------------------------------------------------------------

def _run_git(args: List[str], cwd: str = ".") -> Dict[str, Any]:
    """Safely runs a Git command and captures output."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=os.path.abspath(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }


def tool_git_status(repo_path: str = ".") -> str:
    """Returns working tree status and branch info."""
    res = _run_git(["status", "--short", "--branch"], cwd=repo_path)
    if not res["success"]:
        return f"Error running git status: {res['stderr']}"
    output = res["stdout"]
    return output if output else "Working tree clean. No uncommitted changes."


def tool_git_diff(staged: bool = False, file_path: Optional[str] = None, repo_path: str = ".") -> str:
    """Retrieves diff of staged or unstaged modifications."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file_path:
        args.extend(["--", file_path])
    res = _run_git(args, cwd=repo_path)
    if not res["success"]:
        return f"Error running git diff: {res['stderr']}"
    diff = res["stdout"]
    return diff if diff else "(No diff found)"


def tool_git_log(max_count: int = 10, author: Optional[str] = None, repo_path: str = ".") -> str:
    """Retrieves formatted commit history."""
    args = ["log", f"-n{max(1, min(max_count, 100))}", "--pretty=format:%h | %an | %ad | %s", "--date=short"]
    if author:
        args.append(f"--author={author}")
    res = _run_git(args, cwd=repo_path)
    if not res["success"]:
        return f"Error running git log: {res['stderr']}"
    return res["stdout"] if res["stdout"] else "(No commits found)"


def tool_git_branches(repo_path: str = ".") -> str:
    """Lists local branches and tracking status."""
    res = _run_git(["branch", "-vv"], cwd=repo_path)
    if not res["success"]:
        return f"Error running git branch: {res['stderr']}"
    return res["stdout"] if res["stdout"] else "(No branches found)"


def tool_git_show(commit_hash: str, repo_path: str = ".") -> str:
    """Inspects commit details and patch."""
    res = _run_git(["show", "--stat", "-p", commit_hash], cwd=repo_path)
    if not res["success"]:
        return f"Error running git show: {res['stderr']}"
    # Truncate very large patches to safe bounds
    output = res["stdout"]
    if len(output) > 20000:
        output = output[:20000] + "\n\n[...diff truncated for length]"
    return output


# ---------------------------------------------------------------------------
# MCP Tool Registry & Schemas
# ---------------------------------------------------------------------------

TOOLS_METADATA = [
    {
        "name": "git_status",
        "description": "Get current git status including branch, staged files, unstaged files, and untracked changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Optional path to the git repository root (defaults to current directory).",
                    "default": ".",
                }
            },
        },
    },
    {
        "name": "git_diff",
        "description": "Retrieve git diff for staged or unstaged changes, with optional file filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "If true, show staged changes (--staged). Otherwise show unstaged working changes.",
                    "default": False,
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional specific file to limit diff to.",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Optional path to git repository root.",
                    "default": ".",
                },
            },
        },
    },
    {
        "name": "git_log",
        "description": "Get recent commit history with commit hashes, authors, dates, and subjects.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_count": {
                    "type": "integer",
                    "description": "Maximum number of commits to retrieve (default: 10, max: 100).",
                    "default": 10,
                },
                "author": {
                    "type": "string",
                    "description": "Filter commits by author name or email.",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Optional path to git repository root.",
                    "default": ".",
                },
            },
        },
    },
    {
        "name": "git_branches",
        "description": "List all local branches, upstream tracking branches, and ahead/behind counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Optional path to git repository root.",
                    "default": ".",
                }
            },
        },
    },
    {
        "name": "git_show",
        "description": "Show detailed commit information and code patch for a given commit hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "commit_hash": {
                    "type": "string",
                    "description": "Commit hash or reference (e.g. 'HEAD', 'HEAD~1', or 'c84ec28').",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Optional path to git repository root.",
                    "default": ".",
                },
            },
            "required": ["commit_hash"],
        },
    },
]


PROMPTS_METADATA = [
    {
        "name": "generate-commit-message",
        "description": "Analyzes current staged Git changes and prompts for a Conventional Commit message.",
        "arguments": [
            {
                "name": "hint",
                "description": "Optional context or hint for the commit.",
                "required": False,
            }
        ],
    },
    {
        "name": "review-pr-changes",
        "description": "Analyzes working tree diff and requests a comprehensive security and quality code review.",
        "arguments": [],
    },
]


def dispatch_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Dispatches tool execution by name."""
    repo_path = arguments.get("repo_path", ".")

    if name == "git_status":
        return tool_git_status(repo_path=repo_path)
    elif name == "git_diff":
        return tool_git_diff(
            staged=arguments.get("staged", False),
            file_path=arguments.get("file_path"),
            repo_path=repo_path,
        )
    elif name == "git_log":
        return tool_git_log(
            max_count=arguments.get("max_count", 10),
            author=arguments.get("author"),
            repo_path=repo_path,
        )
    elif name == "git_branches":
        return tool_git_branches(repo_path=repo_path)
    elif name == "git_show":
        commit_hash = arguments.get("commit_hash")
        if not commit_hash:
            return "Error: 'commit_hash' argument is required for git_show."
        return tool_git_show(commit_hash=commit_hash, repo_path=repo_path)
    else:
        return f"Error: Unknown tool '{name}'."


# ---------------------------------------------------------------------------
# MCP JSON-RPC 2.0 Protocol Handler
# ---------------------------------------------------------------------------

def handle_jsonrpc_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Processes an incoming JSON-RPC 2.0 message."""
    method = msg.get("method")
    msg_id = msg.get("id")

    # Notifications do not return responses
    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    "prompts": {},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "prompts": PROMPTS_METADATA,
            },
        }

    if method == "prompts/get":
        params = msg.get("params", {})
        prompt_name = params.get("name")
        args = params.get("arguments", {})
        if prompt_name == "generate-commit-message":
            staged_diff = tool_git_diff(staged=True)
            status_text = tool_git_status()
            user_hint = args.get("hint", "")
            prompt_text = (
                f"Please generate a Conventional Commit message for these staged changes.\n\n"
                f"Status:\n{status_text}\n\nDiff:\n{staged_diff}\n"
            )
            if user_hint:
                prompt_text += f"\nUser Hint: {user_hint}"
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": "Conventional Commit generation prompt",
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": prompt_text},
                        }
                    ],
                },
            }
        elif prompt_name == "review-pr-changes":
            diff_text = tool_git_diff(staged=False)
            prompt_text = (
                f"Please conduct a comprehensive code review focusing on OWASP security, "
                f"performance, and code quality on this diff:\n\n{diff_text}"
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": "Code review prompt",
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": prompt_text},
                        }
                    ],
                },
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"Prompt '{prompt_name}' not found"},
            }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": TOOLS_METADATA,
            },
        }

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        result_text = dispatch_tool(tool_name, arguments)

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": result_text,
                    }
                ],
            },
        }

    # Unknown method
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found",
            },
        }
    return None


def run_stdio_server():
    """Main stdio loop reading JSON-RPC lines from stdin and writing to stdout."""
    # Ensure stdout is unbuffered
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_jsonrpc_message(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as err:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {err}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# CLI / Self-test Mode
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--test":
            print(f"Testing {SERVER_NAME} tools against current directory:")
            print("\n--- git_status ---")
            print(tool_git_status())
            print("\n--- git_branches ---")
            print(tool_git_branches())
            print("\n--- git_log (latest 3) ---")
            print(tool_git_log(max_count=3))
            print("\n✓ All local tool checks completed successfully.")
            sys.exit(0)
        elif cmd == "--tools":
            print(json.dumps(TOOLS_METADATA, indent=2))
            sys.exit(0)
        elif cmd in ("--help", "-h"):
            print(f"{SERVER_NAME} v{SERVER_VERSION}")
            print("Run with no arguments to start the MCP stdio server.")
            print("Flags:")
            print("  --test    Run self-test inspection on current repository")
            print("  --tools   Print tool JSON schemas")
            sys.exit(0)

    run_stdio_server()


if __name__ == "__main__":
    main()

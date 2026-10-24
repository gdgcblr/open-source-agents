"""Model Context Protocol (MCP) Server for BlastRadius.

Exposes BlastRadius change impact analysis tools over standard JSON-RPC 2.0 (stdio)
compatible with Claude Desktop, Cursor, Antigravity, and other MCP clients.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

from .agent import BlastRadiusAgent
from .java_analyzer import JavaAnalyzer
from .test_recommender import TestRecommender
from .reporter import ImpactReporter

SERVER_NAME = "blast-radius-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "analyze_change_impact",
        "description": "Analyzes a Git diff against a Java microservice repository, mapping changed methods, direct callers, test coverage gaps, and recommended tests.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "Unified Git diff content."
                },
                "repo_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the Java repository root (default: current directory)."
                }
            },
            "required": ["diff"]
        }
    },
    {
        "name": "find_method_callers",
        "description": "Discovers all direct production and test invocation call sites for a given Java method across the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "method_name": {
                    "type": "string",
                    "description": "Name of the Java method to search (e.g., 'processPayment')."
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to the Java repository root (default: current directory)."
                }
            },
            "required": ["method_name"]
        }
    },
    {
        "name": "recommend_test_targets",
        "description": "Recommends prioritized test targets and synthesizes ready-to-run Maven test commands for a given Git diff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "Unified Git diff content."
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to the Java repository root (default: current directory)."
                }
            },
            "required": ["diff"]
        }
    }
]


class MCPServer:
    """Standard JSON-RPC 2.0 stdio MCP Server implementation."""

    def __init__(self):
        self.running = True

    def run(self):
        """Main stdio loop reading JSON-RPC requests."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
                sys.stdout.write(json.dumps(err_response) + "\n")
                sys.stdout.flush()

    def handle_request(self, req: Dict[str, Any]) -> Any:
        method = req.get("method")
        msg_id = req.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    },
                    "capabilities": {
                        "tools": {}
                    }
                }
            }

        elif method == "notifications/initialized":
            # Handshake notification, no response required
            return None

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {}
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOLS
                }
            }

        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {})

            try:
                output_text = self.execute_tool(tool_name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": output_text
                            }
                        ]
                    }
                }
            except Exception as err:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{tool_name}': {str(err)}"
                            }
                        ]
                    }
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found."
                }
            }

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        repo_path = args.get("repo_path", ".")

        if tool_name == "analyze_change_impact":
            diff = args["diff"]
            agent = BlastRadiusAgent(repo_path=repo_path)
            report = agent.analyze_diff(diff)
            return ImpactReporter.to_markdown(report)

        elif tool_name == "find_method_callers":
            method_name = args["method_name"]
            analyzer = JavaAnalyzer(Path(repo_path))
            callers = analyzer.find_direct_callers(method_name)

            if not callers:
                return f"No callers found for method `{method_name}` in `{repo_path}`."

            lines = [f"Found {len(callers)} caller(s) for `{method_name}`:"]
            for c in callers:
                tag = "Test" if c.is_test else "Production"
                lines.append(f"- [{tag}] {c.caller_file}#L{c.call_line} ({c.caller_class}#{c.caller_method}): `{c.code_snippet}`")
            return "\n".join(lines)

        elif tool_name == "recommend_test_targets":
            diff = args["diff"]
            agent = BlastRadiusAgent(repo_path=repo_path)
            report = agent.analyze_diff(diff)

            if not report.recommended_tests:
                return "No existing unit or integration tests were detected for the modified methods."

            lines = ["### Recommended Tests:"]
            for t in report.recommended_tests:
                method_part = f"#{t.test_method}" if t.test_method else ""
                lines.append(f"- [{t.priority}] `{t.test_class}{method_part}` ({t.test_file}): {t.reason}")

            test_targets = {
                f"{t.test_class}#{t.test_method}" if t.test_method else t.test_class
                for t in report.recommended_tests if t.test_class
            }
            lines.append(f"\nMaven command:\n`mvn test -Dtest={','.join(sorted(test_targets))}`")
            return "\n".join(lines)

        else:
            raise ValueError(f"Unknown tool name: {tool_name}")


def main():
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()


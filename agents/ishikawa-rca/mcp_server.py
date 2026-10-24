"""MCP server: use Ishikawa's investigation and its guardrails from any MCP client.

    python mcp_server.py                      # stdio (Claude Desktop, Cursor, ADK MCPToolset, ...)

Tools:
  list_incidents     bundled incidents
  investigate        full multi-agent RCA (live with credentials, else recorded replay)
  sanitize_evidence  the input guardrail as a service: redact secrets/PII, quarantine injected instructions
  check_fix          the output guardrail as a service: is this remediation command safe to suggest?
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mcp.server.mcpserver import MCPServer  # noqa: E402

from ishikawa import guardrails as g  # noqa: E402
from ishikawa.replay import audit_path, has_recording, record, replay  # noqa: E402
from ishikawa.runner import investigate as run_investigation  # noqa: E402
from ishikawa.tools import list_incidents as _list_incidents  # noqa: E402
from server import live_available  # noqa: E402

mcp = MCPServer("ishikawa-rca")


@mcp.tool()
def list_incidents() -> list[dict]:
    """List the bundled incidents that can be investigated."""
    return _list_incidents()


@mcp.tool()
async def investigate(incident_id: str, mode: str = "auto") -> dict:
    """Run a fishbone root-cause analysis. mode: auto | live | replay. Returns the RCA report,
    guardrail decision and run metrics. The suggested fix is never executed; a human must approve it."""
    use_replay = mode == "replay" or (mode == "auto" and not live_available())
    if use_replay and not has_recording(incident_id):
        return {"error": f"no recording for {incident_id}"}
    events = replay(incident_id, speed=20) if use_replay else record(
        run_investigation(incident_id), incident_id, dest=audit_path(incident_id))
    result: dict = {"mode": "replay" if use_replay else "live"}
    async for ev in events:
        if ev["type"] == "report":
            result.update(report=ev["report"], guardrails=ev["guardrails"], metrics=ev["metrics"])
    return result


@mcp.tool()
def sanitize_evidence(text: str) -> dict:
    """Redact secrets/PII and quarantine lines that try to instruct an AI, before any model reads `text`."""
    return g.sanitize_text(text, "sanitize_evidence")


@mcp.tool()
def check_fix(command: str) -> dict:
    """Check a proposed remediation command against Ishikawa's allowlist (no shell metacharacters)."""
    ok, reason = g.check_fix(command)
    return {"allowed": ok, "reason": reason}


if __name__ == "__main__":
    mcp.run()

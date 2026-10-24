"""Safe MCP interface for the local Fix Maadi civic routing agent."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP


BASE_URL = os.getenv("FIX_MAADI_URL", "http://127.0.0.1:8000").rstrip("/")
mcp = FastMCP("fix-maadi")


def _request(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(urljoin(BASE_URL + "/", path.lstrip("/")), data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


@mcp.tool()
def analyze_civic_report(description: str, location: str = "", landmark: str = "", observed_at: str = "", duration: str = "") -> dict[str, Any]:
    """Classify a civic observation, ask for missing context, and prepare sourced routes."""
    return _request("/api/analyze", "POST", {"description": description, "location": location, "landmark": landmark, "observed_at": observed_at, "duration": duration})


@mcp.tool()
def list_civic_channels(category: str = "") -> dict[str, Any]:
    """Read the current source-linked civic channel registry."""
    channels = _request("/api/channels")
    return {category: channels.get(category)} if category else channels


@mcp.tool()
def get_local_case(case_id: str) -> dict[str, Any]:
    """Read one locally saved case for review; this tool cannot modify or submit it."""
    cases = _request("/api/cases")
    return next((case for case in cases if case.get("case_id") == case_id), {"error": "Case not found"})


@mcp.prompt()
def prepare_civic_case(description: str, location: str = "") -> str:
    """Guide an MCP client to prepare a sourced case without external action."""
    return (
        "Prepare a resident-reviewable civic case from this observation. "
        "Call analyze_civic_report, ask only for missing location/time/evidence, "
        "use a source-backed channel, and never invent an authority, SLA, contact, "
        "or outcome. Do not open portals, send messages, bypass login/OTP/CAPTCHA, "
        "or submit anything. Observation: " + description + " Location: " + location
    )


@mcp.prompt()
def review_case_before_handoff(case_id: str) -> str:
    """Guide an MCP client through the human approval gate."""
    return (
        "Review local case " + case_id + ". Call get_local_case, show the resident the "
        "draft, evidence, privacy findings, source, and destination. Ask for explicit "
        "approval. Only after approval may the resident choose copy/open/call; never "
        "perform login, OTP, CAPTCHA, WhatsApp sending, or automatic submission."
    )


@mcp.resource("fix-maadi://safety-rules")
def safety_rules() -> str:
    """Expose the agent's non-negotiable safety boundary to MCP clients."""
    return """Fix Maadi safety rules:
- Use source-backed official routes only.
- Never invent contacts, jurisdiction, SLAs, or resolution outcomes.
- Flag phone numbers and emails for resident redaction review.
- Require explicit resident approval before any handoff.
- Never bypass login, OTP, CAPTCHA, or submit to an external service.
"""


@mcp.resource("fix-maadi://channel-registry")
def channel_registry() -> str:
    """Expose the current registry without duplicating it in the MCP server."""
    return json.dumps(_request("/api/channels"), ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

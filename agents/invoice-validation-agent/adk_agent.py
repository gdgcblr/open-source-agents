"""Optional Google ADK entry point.

Run with the ADK CLI from this directory after installing ``google-adk``.
The tool is deterministic and the agent is instructed that its explanation cannot
override the returned validation status.
"""

from main import validate_invoice

try:
    from google.adk.agents import Agent
except ImportError as exc:  # clear failure when optional dependency is absent
    raise RuntimeError("Install google-adk to run this optional entry point.") from exc


def validate_invoice_tool(invoice: dict, known_invoices: list | None = None) -> dict:
    """Validate an invoice using the same source-of-truth deterministic engine."""
    return validate_invoice(invoice, known_invoices)


root_agent = Agent(
    name="invoice_validation_agent",
    model="gemini-2.5-flash",
    description="Explains deterministic invoice validation results without authorizing payment.",
    instruction=("Always call validate_invoice_tool first. Explain its output faithfully. "
                 "Never change status or authorize payment."),
    tools=[validate_invoice_tool],
)

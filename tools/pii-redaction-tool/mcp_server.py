"""MCP Server for PII Redaction Tool."""
import asyncio
from typing import Any
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ListToolsResult, CallToolResult

from pii_detector import PIIDetector
from redaction_engine import ComplianceRedactor
from guardrails import SecurityGuardrails
from config import settings


# Initialize components
detector = PIIDetector()
redactor = ComplianceRedactor()
guardrails = SecurityGuardrails()


async def list_tools_handler(
    context: ServerRequestContext,
    params: Any
) -> ListToolsResult:
    """List available PII redaction tools."""
    return ListToolsResult(
        tools=[
            Tool(
                name="detect_pii",
                description="Detect PII in text using regex patterns. Returns list of detected PII entities with categories and confidence scores.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to analyze for PII"
                        }
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="redact_pii",
                description="Redact PII from text using specified strategy and compliance mode. Returns redacted text and compliance report.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to redact"
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["full", "partial", "hash", "mask"],
                            "description": "Redaction strategy (default: full)",
                            "default": "full"
                        },
                        "compliance_mode": {
                            "type": "string",
                            "enum": ["GDPR", "CCPA", "HIPAA", "STRICT"],
                            "description": "Compliance mode (default: GDPR)",
                            "default": "GDPR"
                        }
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="check_compliance",
                description="Check if text complies with specified regulation. Returns compliance status and violations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to check for compliance"
                        },
                        "compliance_mode": {
                            "type": "string",
                            "enum": ["GDPR", "CCPA", "HIPAA", "STRICT"],
                            "description": "Compliance mode to check (default: GDPR)",
                            "default": "GDPR"
                        }
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="get_pii_summary",
                description="Get a summary of PII types found in text with counts and categories.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to analyze"
                        }
                    },
                    "required": ["text"]
                }
            )
        ]
    )


async def call_tool_handler(
    context: ServerRequestContext,
    params: Any
) -> CallToolResult:
    """Handle tool calls."""
    try:
        name = params.name
        arguments = params.arguments

        if name == "detect_pii":
            text = arguments["text"]
            guardrails.validate_request(text)
            entities = detector.detect_pii(text)
            filtered = guardrails.filter_entities(entities)

            result = {
                "entities": [
                    {
                        "text": e.text,
                        "category": e.category,
                        "confidence": e.confidence,
                        "start": e.start,
                        "end": e.end,
                        "method": e.detection_method
                    }
                    for e in filtered
                ],
                "total_count": len(filtered)
            }

            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=str(result)
                )]
            )

        elif name == "redact_pii":
            text = arguments["text"]
            strategy = arguments.get("strategy", "full")
            compliance_mode = arguments.get("compliance_mode", "GDPR")

            guardrails.validate_request(text)
            entities = detector.detect_pii(text)
            filtered = guardrails.filter_entities(entities)

            result = redactor.redact_with_compliance(text, filtered, strategy=strategy)
            redactor.compliance_mode = compliance_mode

            guardrails.log_detection(text, filtered)

            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=str(result)
                )]
            )

        elif name == "check_compliance":
            text = arguments["text"]
            compliance_mode = arguments.get("compliance_mode", "GDPR")

            guardrails.validate_request(text)
            entities = detector.detect_pii(text)
            filtered = guardrails.filter_entities(entities)

            # Filter by compliance mode
            redactor.compliance_mode = compliance_mode
            compliant_entities = redactor._filter_by_compliance(filtered)

            result = {
                "compliance_mode": compliance_mode,
                "is_compliant": len(compliant_entities) == 0,
                "violations": len(compliant_entities),
                "violation_details": [
                    {
                        "category": e.category,
                        "text": e.text,
                        "confidence": e.confidence
                    }
                    for e in compliant_entities
                ]
            }

            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=str(result)
                )]
            )

        elif name == "get_pii_summary":
            text = arguments["text"]

            guardrails.validate_request(text)
            entities = detector.detect_pii(text)
            filtered = guardrails.filter_entities(entities)

            # Count by category
            category_counts = {}
            for entity in filtered:
                category_counts[entity.category] = category_counts.get(entity.category, 0) + 1

            result = {
                "total_pii_count": len(filtered),
                "categories": category_counts,
                "confidence_avg": sum(e.confidence for e in filtered) / len(filtered) if filtered else 0
            }

            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=str(result)
                )]
            )

        else:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Unknown tool: {name}"
                )]
            )

    except Exception as e:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )]
        )


async def main():
    """Run the MCP server."""
    server = Server("pii-redaction-server")
    
    # Register handlers
    server.add_request_handler("tools/list", Any, list_tools_handler)
    server.add_request_handler("tools/call", Any, call_tool_handler)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

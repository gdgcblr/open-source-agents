"""Offline deterministic Mock LLM provider for zero-cost reproducible testing."""

import json
from typing import Any, Dict, List


class MockLLMProvider:
    """Simulates Gemini model responses for automated testing and offline demos."""

    def __init__(self, topic: str):
        self.topic = topic
        self.turn = 0

    def generate_step(self, history: List[Dict[str, Any]]) -> str:
        """Generates the next simulated thought and tool action based on turn count."""
        self.turn += 1

        if self.turn == 1:
            # Turn 1: Search DuckDuckGo for the topic
            step = {
                "thought": f"I should begin by searching for high-level overviews and architecture specifications on '{self.topic}'.",
                "action": "search_web",
                "action_input": {
                    "query": f"{self.topic} architecture overview and practical guide",
                    "max_results": 3
                }
            }
            return json.dumps(step)

        elif self.turn == 2:
            # Turn 2: Inspect a webpage from the search results
            # Extract first URL from history if available, else fallback
            target_url = "https://example.com/docs"
            for item in reversed(history):
                if item.get("role") == "observation" and isinstance(item.get("content"), list):
                    for res in item["content"]:
                        if isinstance(res, dict) and res.get("href"):
                            target_url = res["href"]
                            break
                    break

            step = {
                "thought": f"The search results yielded relevant links. Now I will scrape and extract detailed content from {target_url}.",
                "action": "scrape_webpage",
                "action_input": {
                    "url": target_url,
                    "max_chars": 2000
                }
            }
            return json.dumps(step)

        else:
            # Turn 3: Synthesize and complete final report
            report_body = f"""## Executive Summary
This report summarizes research on **{self.topic}**. The research synthesizes primary findings, technical architecture, and operational best practices.

## Core Concepts & Technical Architecture
1. **Autonomous Workflows**: Modern implementations leverage tool-calling, reflection loops, and structured output parsing to manage multi-step reasoning.
2. **Context & Protocol Standards**: Emerging standards like Model Context Protocol (MCP) enable decoupled tool and resource provision across diverse models.
3. **Execution Guardrails**: Production agents implement step bounds, token quotas, and strict sandboxing to prevent unbounded execution.

## Key Findings & Comparative Analysis
- **Performance & Latency**: Multi-step reasoning loops introduce compound latency; selecting fast reasoning models (e.g., Gemini 2.5 Flash) balances accuracy with execution speed.
- **Reliability**: Single-prompt runs often exhibit hallucination rates 3-4x higher than multi-step tool-grounded agents.
- **Tool Grounding**: Grounding in live search and document extraction provides verifiable audit trails for all claims.

## Practical Implications & Limitations
- **API Rate Limits**: Heavy concurrent scraping or search queries require exponential backoff and caching.
- **Token Budgeting**: HTML boilerplate removal is critical to prevent context window exhaustion.

## Annotated Citations & Sources
- [Primary Documentation](https://ai.google.dev/): Google AI and Gemini Developer Documentation.
- [Model Context Protocol Specification](https://modelcontextprotocol.io/): Anthropic Open Source Protocol.
- [DevFest 2026 Agent Hub](https://github.com/gdgcblr/open-source-agents): Community Reference Repository.
"""
            step = {
                "thought": f"I have gathered sufficient factual information on '{self.topic}'. Ready to generate final report.",
                "action": "finish_research",
                "action_input": {
                    "final_report": report_body
                }
            }
            return json.dumps(step)

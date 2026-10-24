"""Enterprise test suite for Model Context Protocol (MCP) Server and HTML Dashboard."""

import os
import shutil
import pytest

from agent.tools.html_dashboard import generate_html_dashboard, _extract_toc, _extract_evidence_cards
from agent.tools.reporter import save_research_artifacts
from mcp_server import create_mcp_server

TEST_DIR = "test_extensions_tmp"


@pytest.fixture(autouse=True)
def cleanup():
    """Ensures test directory is cleaned up before and after tests."""
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    yield
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)


# ==============================================================================
# HTML Dashboard Tests
# ==============================================================================

def test_html_dashboard_generation():
    """Validates that generate_html_dashboard returns self-contained HTML with required sections."""
    topic = "Autonomous Research Systems"
    markdown = """## Executive Summary
Autonomous research systems leverage multi-step reasoning.

## Core Architecture
- Agent reasoning loops
- Tool calling protocols

## Citations
- [Docs](https://example.com)
"""
    metrics = {
        "run_id": "test-uuid-1234",
        "duration_seconds": 2.75,
        "steps_taken": 3,
        "searches_performed": 2,
        "pages_scraped": 1,
        "total_chars_analyzed": 1500,
        "mock_mode": True
    }
    history = [
        {"role": "observation", "content": [{"title": "Agent Overview", "href": "https://example.com", "body": "Overview snippet"}]}
    ]

    html_doc = generate_html_dashboard(topic, markdown, metrics=metrics, history=history)

    assert "<!DOCTYPE html>" in html_doc
    assert topic in html_doc
    assert "test-uuid-1234" in html_doc
    assert "2.75s" in html_doc
    assert "Executive Summary" in html_doc
    assert "Evidence Explorer" in html_doc
    assert "https://example.com" in html_doc


def test_html_dashboard_xss_escaping():
    """Validates that malicious script injection in topic or content is safely escaped."""
    malicious_topic = '<script>alert("XSS Attack")</script>'
    malicious_md = '<img src=x onerror=alert(1)>'
    
    html_doc = generate_html_dashboard(malicious_topic, malicious_md)

    assert '<script>alert("XSS Attack")</script>' not in html_doc
    assert '&lt;script&gt;alert(&quot;XSS Attack&quot;)&lt;/script&gt;' in html_doc
    assert '<img src=x' not in html_doc


def test_toc_extraction():
    """Validates that H2 and H3 markdown headers are cleanly extracted into TOC links."""
    sample_md = """# Document Title
## Section Alpha
Content for alpha.
### Subsection Beta
Content for beta.
## Section Gamma
Content for gamma.
"""
    toc = _extract_toc(sample_md)
    assert len(toc) == 3
    assert toc[0]["title"] == "Section Alpha"
    assert toc[0]["anchor"] == "section-alpha"
    assert toc[1]["title"] == "Subsection Beta"
    assert toc[1]["anchor"] == "subsection-beta"
    assert toc[2]["title"] == "Section Gamma"


def test_reporter_saves_both_markdown_and_html():
    """Validates that save_research_artifacts creates both .md and .html files on disk."""
    topic = "MCP Integration Test"
    content = "## Summary\nTesting dual artifact persistence."
    
    artifacts = save_research_artifacts(topic, content, output_dir=TEST_DIR)

    assert "markdown_path" in artifacts
    assert "html_path" in artifacts
    assert os.path.exists(artifacts["markdown_path"])
    assert os.path.exists(artifacts["html_path"])

    with open(artifacts["html_path"], "r", encoding="utf-8") as f:
        html_data = f.read()
    assert "<!DOCTYPE html>" in html_data
    assert topic in html_data


# ==============================================================================
# Model Context Protocol (MCP) Server Tests
# ==============================================================================

def test_mcp_server_creation():
    """Validates that create_mcp_server initializes FastMCP with expected configuration."""
    server = create_mcp_server()
    assert server is not None
    assert server.name == "ResearchAssistant"


def test_mcp_run_deep_research_tool():
    """Validates that the MCP agent tool can be invoked and returns formatted markdown."""
    from agent.core import ResearchAgent
    agent = ResearchAgent(mock_mode=True, max_steps=3, output_dir=TEST_DIR)
    result = agent.run("MCP Agent Tool Verification")

    assert result["status"] == "completed"
    assert os.path.exists(result["report_path"])
    assert os.path.exists(result["html_path"])
    assert len(result["final_report"]) > 0

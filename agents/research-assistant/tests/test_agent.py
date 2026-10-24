"""Enterprise test suite for Research Assistant Agent and Tools."""

import os
import shutil
import pytest

from agent.exceptions import InvalidTopicError
from agent.schema import AgentStepResponse, ResearchMetrics, ToolActionEnum
from agent.tools.search import search_web
from agent.tools.scraper import scrape_webpage
from agent.tools.reporter import save_markdown_report, sanitize_filename
from agent.mock_provider import MockLLMProvider
from agent.core import ResearchAgent

TEST_OUTPUT_DIR = "test_enterprise_reports_tmp"


@pytest.fixture(autouse=True)
def cleanup():
    """Ensures test output directories are cleaned up before and after each test."""
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)
    yield
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)


# ==============================================================================
# Search Tool Tests
# ==============================================================================

def test_search_tool_happy_path():
    """Validates that search_web returns structured results with title, href, and body."""
    results = search_web("Google Gemini API", max_results=2)
    assert isinstance(results, list)
    assert len(results) > 0
    first = results[0]
    assert "title" in first and len(first["title"]) > 0
    assert "href" in first and first["href"].startswith("http")
    assert "body" in first


def test_search_tool_empty_query():
    """Validates that empty or whitespace queries return an empty list gracefully."""
    assert search_web("") == []
    assert search_web("   ") == []
    assert search_web(None) == []


def test_search_tool_max_results_capping():
    """Validates that max_results is properly bounded between 1 and 10."""
    results_single = search_web("Python programming", max_results=1)
    assert len(results_single) <= 1


# ==============================================================================
# Web Scraper Tool Tests
# ==============================================================================

def test_scraper_invalid_url_schemes():
    """Validates that scrape_webpage safely rejects invalid URLs and non-HTTP schemes."""
    invalid_cases = [
        "not_a_url",
        "",
        None,
        "ftp://example.com/file.txt",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ]
    for case in invalid_cases:
        res = scrape_webpage(case)
        assert res["status"] == "error"
        assert "Invalid URL" in res["content"]


def test_scraper_valid_url_structure():
    """Validates that scrape_webpage returns standard dictionary keys on a live or mock URL."""
    res = scrape_webpage("https://example.com")
    assert "status" in res
    assert "title" in res
    assert "content" in res
    assert "char_count" in res


# ==============================================================================
# Report Exporter & Sanitization Tests
# ==============================================================================

def test_sanitize_filename_prevents_path_traversal():
    """Validates that path traversal attacks and illegal characters are stripped."""
    dangerous_topics = [
        "../../etc/passwd",
        "topic with <illegal>:*?\"/\\| characters",
        "....//....//nested_path",
        "   ---   ",
    ]
    for topic in dangerous_topics:
        slug = sanitize_filename(topic)
        assert "/" not in slug
        assert "\\" not in slug
        assert ".." not in slug
        assert len(slug) > 0


def test_reporter_writes_metrics_frontmatter():
    """Validates that save_markdown_report correctly writes YAML frontmatter with telemetry."""
    topic = "Model Context Protocol Enterprise Testing"
    sample_content = "## Executive Summary\nTesting MCP integration."
    metrics = {
        "duration_seconds": 3.45,
        "steps_taken": 3,
        "pages_scraped": 2,
        "searches_performed": 1,
        "mock_mode": True,
    }

    filepath = save_markdown_report(topic, sample_content, output_dir=TEST_OUTPUT_DIR, metrics=metrics)

    assert os.path.exists(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    assert topic in content
    assert "duration_seconds: 3.45" in content
    assert "steps_taken: 3" in content
    assert "mock_mode: True" in content
    assert "generated_at:" in content


# ==============================================================================
# Mock Engine & Pydantic Schema Tests
# ==============================================================================

def test_mock_provider_lifecycle():
    """Validates that MockLLMProvider produces search, scrape, then finish steps in sequence."""
    mock = MockLLMProvider(topic="Agentic AI")

    # Step 1: Search
    step1 = mock.generate_step([])
    assert "search_web" in step1

    # Step 2: Scrape
    step2 = mock.generate_step([{"role": "observation", "content": [{"href": "https://example.com"}]}])
    assert "scrape_webpage" in step2

    # Step 3: Finish
    step3 = mock.generate_step([])
    assert "finish_research" in step3


def test_pydantic_schema_validation():
    """Validates Pydantic contracts on agent step responses."""
    valid_step = {
        "thought": "I need to search for docs.",
        "action": "search_web",
        "action_input": {"query": "LangGraph overview", "max_results": 3}
    }
    model = AgentStepResponse(**valid_step)
    assert model.action == ToolActionEnum.SEARCH_WEB
    assert model.action_input["query"] == "LangGraph overview"


# ==============================================================================
# Agent Core Engine & Telemetry Tests
# ==============================================================================

def test_agent_empty_topic_raises_exception():
    """Validates that initializing a run with empty or whitespace topic raises InvalidTopicError."""
    agent = ResearchAgent(mock_mode=True, output_dir=TEST_OUTPUT_DIR)
    with pytest.raises(InvalidTopicError):
        agent.run("")
    with pytest.raises(InvalidTopicError):
        agent.run("   ")
    with pytest.raises(InvalidTopicError):
        agent.run(None)


def test_agent_json_parsing_resilience():
    """Validates that ResearchAgent safely cleans code blocks and parses JSON variations."""
    agent = ResearchAgent(mock_mode=True, output_dir=TEST_OUTPUT_DIR)

    # 1. Standard markdown code fence
    markdown_json = '```json\n{"thought": "test", "action": "finish_research", "action_input": {}}\n```'
    parsed1 = agent._clean_json_response(markdown_json)
    assert parsed1["action"] == "finish_research"

    # 2. Text with leading and trailing whitespace
    raw_json = '   {"thought": "ok", "action": "search_web", "action_input": {"query": "test"}}   '
    parsed2 = agent._clean_json_response(raw_json)
    assert parsed2["action"] == "search_web"

    # 3. Invalid syntax raises ValueError
    with pytest.raises(ValueError):
        agent._clean_json_response("This is not JSON at all.")


def test_agent_end_to_end_mock_with_telemetry():
    """Validates complete end-to-end execution of ResearchAgent in mock mode with full telemetry."""
    steps_logged = []

    def callback(record):
        steps_logged.append(record)

    agent = ResearchAgent(
        mock_mode=True,
        output_dir=TEST_OUTPUT_DIR,
        step_callback=callback
    )

    result = agent.run("Enterprise Comparative Analysis of Agent Frameworks")

    assert result["status"] == "completed"
    assert result["steps_taken"] == 3
    assert os.path.exists(result["report_path"])
    assert len(result["final_report"]) > 100
    assert len(steps_logged) >= 3

    # Assert telemetry metrics
    metrics = result["metrics"]
    assert "run_id" in metrics
    assert metrics["topic"] == "Enterprise Comparative Analysis of Agent Frameworks"
    assert metrics["duration_seconds"] >= 0.0
    assert metrics["steps_taken"] == 3
    assert metrics["searches_performed"] >= 1
    assert metrics["pages_scraped"] >= 1
    assert metrics["total_chars_analyzed"] > 0
    assert metrics["mock_mode"] is True

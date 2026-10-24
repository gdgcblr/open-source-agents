"""Enterprise Pydantic schemas and typed data contracts."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolActionEnum(str, Enum):
    """Supported agent tool actions."""
    SEARCH_WEB = "search_web"
    SCRAPE_WEBPAGE = "scrape_webpage"
    FINISH_RESEARCH = "finish_research"


class SearchResultItem(BaseModel):
    """Standardized search result contract."""
    title: str = Field(..., description="Page title")
    href: str = Field(..., description="Direct URL")
    body: str = Field(..., description="Snippet text summary")


class ScrapedDocument(BaseModel):
    """Standardized scraped webpage contract."""
    url: str
    title: str
    status: str
    content: str
    char_count: int = 0


class AgentStepResponse(BaseModel):
    """Structured step response contract for LLM outputs."""
    thought: str = Field(..., description="Chain-of-thought rationale")
    action: ToolActionEnum = Field(..., description="Action to perform")
    action_input: Dict[str, Any] = Field(default_factory=dict, description="Input parameters")


class ResearchMetrics(BaseModel):
    """Operational telemetry and audit metrics for an agent run."""
    run_id: str
    topic: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    steps_taken: int = 0
    searches_performed: int = 0
    pages_scraped: int = 0
    total_chars_analyzed: int = 0
    mock_mode: bool = False


class ResearchExecutionResult(BaseModel):
    """Complete typed execution result payload."""
    status: str
    topic: str
    final_report: str
    report_path: str
    metrics: ResearchMetrics
    history: List[Dict[str, Any]] = Field(default_factory=list)

"""
schemas.py - Typed Schema for Research Artifact Extraction
"""
from typing import List, Optional
from pydantic import BaseModel, Field

class ExtractedTable(BaseModel):
    title: str = Field(..., description="Descriptive title of the benchmark or evaluation table")
    headers: List[str] = Field(..., description="Column names")
    rows: List[List[str]] = Field(..., description="2D matrix of row cells")

class ResearchPaperArtifacts(BaseModel):
    title: str = Field(..., description="Formal paper title")
    authors: Optional[str] = Field(default=None, description="Identified authors or institutions")
    executive_summary: str = Field(..., description="Executive problem formulation, motivation, and solution")
    key_insights: List[str] = Field(..., description="3 to 5 critical algorithmic, systems, or technical insights")
    limitations_and_tradeoffs: List[str] = Field(..., description="Hardware bottlenecks, failure modes, KV-cache or latency bounds")
    comparative_table: ExtractedTable = Field(..., description="A concrete benchmark or taxonomy table")
    diagram_mermaid: str = Field(..., description="Valid Mermaid.js flowchart (starting with flowchart TD or graph TD)")
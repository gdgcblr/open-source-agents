"""Unit tests for pdf-hierarchy-parser.

Uses hardcoded mock items matching Docling's verified output. No Docling
dependency means instant pytest runs and offline CI.
"""

from __future__ import annotations

import networkx as nx
import pytest

from pdf_parser.chunker import hierarchical_chunk
from pdf_parser.graph import build_hierarchy_graph, infer_heading_level
from pdf_parser.query import export_graph_json, get_node_breadcrumbs, get_subtree

MOCK_SAMPLE_ITEMS = [
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "Cloud Agent Architecture & Operational Blueprint", "index": 0},
    {"class": "TextItem", "label": "text",
     "text": "A Reference Guide for Hierarchy-Preserving Agent Retrieval Systems", "index": 1},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "1. Executive Summary & Core Objectives", "index": 2},
    {"class": "TextItem", "label": "text",
     "text": "Modern autonomous agents require access to complex technical documents.", "index": 3},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "2. System Topology & Core Components", "index": 4},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "2.1 Ingestion and Layout Parsing", "index": 5},
    {"class": "ListItem", "label": "list_item",
     "text": "Heading Elements: Titles, Subsections, and Captions.", "index": 6},
    {"class": "ListItem", "label": "list_item",
     "text": "Content Elements: Paragraphs, Code Blocks, and Lists.", "index": 7},
    {"class": "ListItem", "label": "list_item",
     "text": "Structured Elements: Tables with cells, rows, and headers.", "index": 8},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "2.2 Hierarchical Graph Construction", "index": 9},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "2.2.1 Edge Classification & Relationship Semantics", "index": 10},
    {"class": "TextItem", "label": "text",
     "text": "The NetworkX DiGraph builder instantiates two primary edge types.", "index": 11},
    {"class": "TableItem", "label": "table", "text": "", "index": 12},
    {"class": "TextItem", "label": "caption",
     "text": "Table 1: Node Type Specifications & Constraints", "index": 13},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "3. Production Deployment & Verification Guidelines", "index": 14},
    {"class": "SectionHeaderItem", "label": "section_header",
     "text": "3.1 Security Hardening and Zero-Secrets Policy", "index": 15},
    {"class": "TextItem", "label": "text",
     "text": "In compliance with community repository standards.", "index": 16},
]


@pytest.fixture
def sample_graph() -> nx.DiGraph:
    return build_hierarchy_graph(MOCK_SAMPLE_ITEMS)


def _find_node(graph: nx.DiGraph, text_fragment: str) -> str | None:
    for node_id, attrs in graph.nodes(data=True):
        if text_fragment in attrs.get("text", ""):
            return node_id
    return None


class TestInferHeadingLevel:
    def test_numbered_single_digit(self):
        assert infer_heading_level("1. Foo", prev_level=1) == 1
        assert infer_heading_level("5 Baz", prev_level=2) == 1

    def test_numbered_multi_level(self):
        assert infer_heading_level("3.2.1 Foo", prev_level=1) == 3
        assert infer_heading_level("3.2.1. Foo", prev_level=1) == 3

    def test_known_keywords(self):
        assert infer_heading_level("Abstract", prev_level=3) == 1
        assert infer_heading_level("References", prev_level=3) == 1
        assert infer_heading_level("Conclusion", prev_level=2) == 1
        assert infer_heading_level("Related Work", prev_level=3) == 1

    def test_unnumbered_fallback(self):
        assert infer_heading_level("Scaled Dot-Product Attention", prev_level=2) == 3


class TestGraphStructure:
    def test_graph_has_root(self, sample_graph):
        assert "root" in sample_graph
        assert sample_graph.nodes["root"]["level"] == -1

    def test_title_is_level_0(self, sample_graph):
        title_id = _find_node(sample_graph, "Cloud Agent Architecture")
        assert title_id is not None
        assert sample_graph.nodes[title_id]["type"] == "title"
        assert sample_graph.nodes[title_id]["level"] == 0

    def test_section_nesting(self, sample_graph):
        sec2 = _find_node(sample_graph, "2. System Topology")
        sec21 = _find_node(sample_graph, "2.1 Ingestion")
        assert sec2 is not None and sec21 is not None
        assert sample_graph.nodes[sec2]["level"] == 1
        assert sample_graph.nodes[sec21]["level"] == 2
        assert list(sample_graph.successors(sec2))[0] == sec21

    def test_subsection_nesting(self, sample_graph):
        sec22 = _find_node(sample_graph, "2.2 Hierarchical Graph")
        sec221 = _find_node(sample_graph, "2.2.1 Edge Classification")
        assert sec22 is not None and sec221 is not None
        assert sample_graph.nodes[sec22]["level"] == 2
        assert sample_graph.nodes[sec221]["level"] == 3
        assert list(sample_graph.successors(sec22))[0] == sec221

    def test_leaf_attachment(self, sample_graph):
        sec21 = _find_node(sample_graph, "2.1 Ingestion")
        assert sec21 is not None
        children = list(sample_graph.successors(sec21))
        leaf_texts = [sample_graph.nodes[c]["text"] for c in children]
        assert "Heading Elements: Titles" in leaf_texts[0]
        assert all(sample_graph.nodes[c]["type"] == "list_item" for c in children)

    def test_breadcrumbs_propagation(self, sample_graph):
        sec221 = _find_node(sample_graph, "2.2.1 Edge Classification")
        assert sec221 is not None
        crumbs = sample_graph.nodes[sec221]["breadcrumbs"]
        assert crumbs == [
            "Cloud Agent Architecture & Operational Blueprint",
            "2. System Topology & Core Components",
            "2.2 Hierarchical Graph Construction",
            "2.2.1 Edge Classification & Relationship Semantics",
        ]


class TestChunker:
    def test_chunker_breadcrumb_prefix(self, sample_graph):
        chunks = hierarchical_chunk(sample_graph, max_chars=1500)
        sec31_chunks = [c for c in chunks if "3.1 Security" in c["heading"]]
        assert sec31_chunks, "expected a chunk for 3.1"
        prefix = sec31_chunks[0]["header_prefix"]
        assert prefix.startswith("[Cloud Agent Architecture & Operational Blueprint > 3. Production Deployment & Verification Guidelines > 3.1 Security Hardening and Zero-Secrets Policy]")

    def test_chunker_content(self, sample_graph):
        chunks = hierarchical_chunk(sample_graph, max_chars=1500)
        sec31 = next(c for c in chunks if "3.1 Security" in c["heading"])
        assert "In compliance with community repository standards." in sec31["content"]

    def test_chunker_max_chars_split(self, sample_graph):
        chunks = hierarchical_chunk(sample_graph, max_chars=20)
        sec31_chunks = [c for c in chunks if "3.1 Security" in c["heading"]]
        assert len(sec31_chunks) > 1
        for c in sec31_chunks:
            assert len(c["content"]) <= 20
            assert c["text_with_context"].startswith(c["header_prefix"])

    def test_chunker_skips_empty_headings(self, sample_graph):
        chunks = hierarchical_chunk(sample_graph, max_chars=1500)
        # TableItem has empty text, caption is not a heading
        headings = [c["heading"] for c in chunks]
        assert not any("Table" in h for h in headings)


class TestQuery:
    def test_query_subtree(self, sample_graph):
        subtree = get_subtree(sample_graph, "System Topology")
        assert subtree is not None
        texts = {n["text"] for n in subtree.nodes.values()}
        assert "2.1 Ingestion and Layout Parsing" in texts
        assert "2.2.1 Edge Classification & Relationship Semantics" in texts

    def test_query_missing(self, sample_graph):
        assert get_subtree(sample_graph, "nonexistent") is None

    def test_query_case_insensitive(self, sample_graph):
        subtree = get_subtree(sample_graph, "system topology")
        assert subtree is not None

    def test_get_node_breadcrumbs(self, sample_graph):
        sec221 = _find_node(sample_graph, "2.2.1 Edge Classification")
        assert sec221 is not None
        crumbs = get_node_breadcrumbs(sample_graph, sec221)
        assert crumbs[0] == "Cloud Agent Architecture & Operational Blueprint"
        assert crumbs[-1] == "2.2.1 Edge Classification & Relationship Semantics"

    def test_export_json_structure(self, sample_graph):
        payload = export_graph_json(sample_graph)
        assert "nodes" in payload and "edges" in payload
        assert all("id" in n and "type" in n and "text" in n for n in payload["nodes"])
        assert all("source" in e and "target" in e for e in payload["edges"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
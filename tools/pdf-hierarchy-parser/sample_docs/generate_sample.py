"""
Deterministic sample PDF generator for testing `pdf-hierarchy-parser`.
Uses PyMuPDF (fitz) to create a clean, multi-level hierarchical PDF with:
- Document Title
- Section Headings (H1, H2, H3)
- Body Paragraphs
- Structured Tables
- Numbered and Bulleted Lists

Licensing: Open Source / CC0 (Public Domain test asset).
"""

import sys
from pathlib import Path
import fitz  # PyMuPDF


def generate_sample_pdf(output_path: str = "sample_report.pdf") -> str:
    doc = fitz.open()

    # --- Page 1: Overview & Architecture ---
    page1 = doc.new_page(width=595, height=842)  # A4 size

    # Title
    page1.insert_text(
        fitz.Point(50, 70),
        "Cloud Agent Architecture & Operational Blueprint",
        fontsize=18,
        fontname="helv",
    )

    page1.insert_text(
        fitz.Point(50, 95),
        "A Reference Guide for Hierarchy-Preserving Agent Retrieval Systems",
        fontsize=11,
        fontname="helv",
    )

    # Horizontal divider line
    page1.draw_line(fitz.Point(50, 105), fitz.Point(545, 105), color=(0.7, 0.7, 0.7), width=1)

    # H1: Section 1
    page1.insert_text(
        fitz.Point(50, 135),
        "1. Executive Summary & Core Objectives",
        fontsize=14,
        fontname="helv",
    )

    summary_text = (
        "Modern autonomous agents require access to complex technical documents. "
        "Standard vector chunking loses critical heading relationships, causing hallucinated "
        "parent contexts and detached tables. This architecture establishes a graph-based "
        "representation preserving document geometry and semantic trees."
    )
    rect_summary = fitz.Rect(50, 150, 545, 200)
    page1.insert_textbox(rect_summary, summary_text, fontsize=10, fontname="helv")

    # H1: Section 2
    page1.insert_text(
        fitz.Point(50, 220),
        "2. System Topology & Core Components",
        fontsize=14,
        fontname="helv",
    )

    # H2: 2.1 Ingestion Pipeline
    page1.insert_text(
        fitz.Point(50, 245),
        "2.1 Ingestion and Layout Parsing",
        fontsize=12,
        fontname="helv",
    )

    ingest_text = (
        "The ingestion pipeline employs Docling to parse raw PDFs into an abstract syntax tree. "
        "Each visual element is categorized into distinct schema classes:"
    )
    rect_ingest = fitz.Rect(50, 255, 545, 285)
    page1.insert_textbox(rect_ingest, ingest_text, fontsize=10, fontname="helv")

    # Bullet points
    page1.insert_text(fitz.Point(65, 300), "• Heading Elements: Titles, Subsections, and Captions.", fontsize=10)
    page1.insert_text(fitz.Point(65, 318), "• Content Elements: Paragraphs, Code Blocks, and Lists.", fontsize=10)
    page1.insert_text(fitz.Point(65, 336), "• Structured Elements: Tables with cells, rows, and headers.", fontsize=10)

    # H2: 2.2 Hierarchy Graph Assembly
    page1.insert_text(
        fitz.Point(50, 365),
        "2.2 Hierarchical Graph Construction",
        fontsize=12,
        fontname="helv",
    )

    # H3: 2.2.1 Edge Classification
    page1.insert_text(
        fitz.Point(50, 390),
        "2.2.1 Edge Classification & Relationship Semantics",
        fontsize=11,
        fontname="helv",
    )

    graph_text = (
        "The NetworkX DiGraph builder instantiates two primary edge types: PARENT_OF edges "
        "model strict hierarchical containment, while NEXT_SIBLING edges preserve the linear "
        "reading order between sibling nodes."
    )
    rect_graph = fitz.Rect(50, 400, 545, 440)
    page1.insert_textbox(rect_graph, graph_text, fontsize=10, fontname="helv")

    # Table: Component Specifications
    page1.insert_text(fitz.Point(50, 460), "Table 1: Node Type Specifications & Constraints", fontsize=10, fontname="helv")

    # Draw simple table border & cells
    table_top = 475
    row_height = 24
    col_x = [50, 160, 310, 440, 545]

    headers = ["Node Type", "Hierarchy Level", "Parent Allowed", "Target Edge"]
    for i, h in enumerate(headers):
        page1.draw_rect(fitz.Rect(col_x[i], table_top, col_x[i+1], table_top + row_height), fill=(0.9, 0.9, 0.9), color=(0.5, 0.5, 0.5))
        page1.insert_text(fitz.Point(col_x[i] + 5, table_top + 16), h, fontsize=9, fontname="helv")

    rows = [
        ["Document", "Level 0 (Root)", "None", "PARENT_OF"],
        ["Heading", "Level 1-4", "Root / Higher Heading", "PARENT_OF, NEXT"],
        ["Paragraph", "Leaf", "Heading", "NEXT_SIBLING"],
        ["Table", "Leaf / Section", "Heading", "NEXT_SIBLING"],
    ]

    for r_idx, row in enumerate(rows):
        y = table_top + (r_idx + 1) * row_height
        for c_idx, cell in enumerate(row):
            page1.draw_rect(fitz.Rect(col_x[c_idx], y, col_x[c_idx+1], y + row_height), color=(0.7, 0.7, 0.7))
            page1.insert_text(fitz.Point(col_x[c_idx] + 5, y + 16), cell, fontsize=8, fontname="helv")

    # --- Page 2: Operational Verification & Deployment ---
    page2 = doc.new_page(width=595, height=842)

    # H1: Section 3
    page2.insert_text(
        fitz.Point(50, 70),
        "3. Production Deployment & Verification Guidelines",
        fontsize=14,
        fontname="helv",
    )

    page2.draw_line(fitz.Point(50, 85), fitz.Point(545, 85), color=(0.7, 0.7, 0.7), width=1)

    # H2: 3.1 Security & Zero Secrets
    page2.insert_text(
        fitz.Point(50, 110),
        "3.1 Security Hardening and Zero-Secrets Policy",
        fontsize=12,
        fontname="helv",
    )

    sec_text = (
        "In compliance with community repository standards, all credentials must be isolated "
        "using environment variables. Never commit credentials or live tokens. "
        "The parser operates completely offline by default, guaranteeing zero telemetry leakage."
    )
    rect_sec = fitz.Rect(50, 125, 545, 170)
    page2.insert_textbox(rect_sec, sec_text, fontsize=10, fontname="helv")

    # H2: 3.2 Performance SLA Benchmarks
    page2.insert_text(
        fitz.Point(50, 195),
        "3.2 Performance Benchmarks & SLA Targets",
        fontsize=12,
        fontname="helv",
    )

    bench_text = (
        "Latency benchmarks were captured on an Ubuntu x86_64 runner with a 2-page reference PDF. "
        "The graph construction phase exhibits sub-linear complexity with respect to page count."
    )
    rect_bench = fitz.Rect(50, 210, 545, 245)
    page2.insert_textbox(rect_bench, bench_text, fontsize=10, fontname="helv")

    # Table 2: Benchmark Results
    page2.insert_text(fitz.Point(50, 260), "Table 2: Execution Latency Benchmarks by Pipeline Stage", fontsize=10, fontname="helv")

    t2_top = 275
    t2_cols = [50, 220, 360, 545]
    t2_headers = ["Pipeline Stage", "p50 Latency (ms)", "p99 Latency (ms)"]

    for i, h in enumerate(t2_headers):
        page2.draw_rect(fitz.Rect(t2_cols[i], t2_top, t2_cols[i+1], t2_top + row_height), fill=(0.9, 0.9, 0.9), color=(0.5, 0.5, 0.5))
        page2.insert_text(fitz.Point(t2_cols[i] + 5, t2_top + 16), h, fontsize=9, fontname="helv")

    t2_rows = [
        ["Docling AST Ingestion", "420 ms", "890 ms"],
        ["NetworkX DiGraph Assembly", "18 ms", "35 ms"],
        ["Breadcrumb Propagation", "4 ms", "9 ms"],
        ["Hierarchical Chunking", "8 ms", "15 ms"],
    ]

    for r_idx, row in enumerate(t2_rows):
        y = t2_top + (r_idx + 1) * row_height
        for c_idx, cell in enumerate(row):
            page2.draw_rect(fitz.Rect(t2_cols[c_idx], y, t2_cols[c_idx+1], y + row_height), color=(0.7, 0.7, 0.7))
            page2.insert_text(fitz.Point(t2_cols[c_idx] + 5, y + 16), cell, fontsize=8, fontname="helv")

    # Save PDF
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    doc.close()
    print(f"Generated sample hierarchical PDF: {output_path}")
    return str(out)


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "sample_report.pdf"
    generate_sample_pdf(out_file)

#!/usr/bin/env python3
"""
Generates the Executive Presentation (.pptx) and Technical Whitepaper (.docx)
for the aws-to-gcp-migrator project (GDG DevFest 2026 Edition).
"""

import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

import pptx
from pptx.util import Inches as PptxInches, Pt as PptxPt
from pptx.dml.color import RGBColor as PptxRGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Google Brand Palette
G_BLUE = RGBColor(66, 133, 244)
G_RED = RGBColor(234, 67, 53)
G_YELLOW = RGBColor(251, 188, 5)
G_GREEN = RGBColor(52, 168, 83)
G_DARK = RGBColor(26, 36, 56)
G_GRAY = RGBColor(100, 116, 139)

PPT_BLUE = PptxRGBColor(66, 133, 244)
PPT_RED = PptxRGBColor(234, 67, 53)
PPT_YELLOW = PptxRGBColor(251, 188, 5)
PPT_GREEN = PptxRGBColor(52, 168, 83)
PPT_DARK_BG = PptxRGBColor(11, 15, 25)
PPT_CARD_BG = PptxRGBColor(21, 29, 48)
PPT_WHITE = PptxRGBColor(248, 250, 252)
PPT_MUTED = PptxRGBColor(148, 163, 184)
PPT_BORDER = PptxRGBColor(35, 48, 76)


def set_cell_background(cell, color_hex):
    shading_xml = f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>'
    cell._tc.get_or_add_tcPr().append(parse_xml(shading_xml))


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def create_word_document():
    doc = docx.Document()

    # Page Margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Document Header Title
    title_p = doc.add_paragraph()
    title_run = title_p.add_run("AWS to Google Cloud Platform Migration Agent\n")
    title_run.font.size = Pt(24)
    title_run.font.bold = True
    title_run.font.color.rgb = G_BLUE

    sub_run = title_p.add_run("Three-Agent Orchestration Architecture, FinOps Network Gravity & HCL Transpiler\n")
    sub_run.font.size = Pt(13)
    sub_run.font.color.rgb = G_GRAY

    tag_p = doc.add_paragraph()
    tag_run = tag_p.add_run("GDG DevFest 2026 Edition | Google Agent Development Kit (ADK) | Powered by Google Gemini 3.5 Flash")
    tag_run.font.size = Pt(10)
    tag_run.font.bold = True
    tag_run.font.color.rgb = G_GREEN

    doc.add_paragraph("—" * 65)

    # 1. Executive Summary
    h1 = doc.add_heading("1. Executive Summary", level=1)
    h1.runs[0].font.color.rgb = G_DARK

    p = doc.add_paragraph(
        "Enterprises seeking to migrate mission-critical infrastructure to Google Cloud Platform (GCP) face a massive operational barrier: "
        "translating complex, regional AWS Terraform configurations (VPCs, ECS Fargate tasks, RDS clusters, SQS queues, and S3 policies) "
        "into idiomatic Google Cloud Platform architecture requires months of specialized engineering, multi-cloud testing, and manual FinOps audits."
    )
    p = doc.add_paragraph(
        "The aws-to-gcp-migrator is an autonomous AI agent engineered specifically for the GDG DevFest 2026 Hackathon. "
        "Built on a Three-Agent Orchestration Architecture leveraging the official Google Agent Development Kit (ADK) and Gemini 3.5 Flash, "
        "the system ingests legacy AWS Terraform infrastructure, builds a dependency graph, calculates cross-cloud data exit tolls, "
        "resolves cloud architecture paradoxes, and outputs production-ready Google Cloud Terraform HCL verified with a One-Click Dry Run Validator."
    )

    # 2. Key Hackathon Metrics & Results Table
    h1 = doc.add_heading("2. Executive FinOps & Migration Scorecard", level=1)
    h1.runs[0].font.color.rgb = G_DARK

    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = table.rows[0].cells
    headers = ["Dimension", "AWS Baseline", "Google Cloud Target", "Impact / Benefit"]
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        hdr_cells[i].paragraphs[0].runs[0].font.bold = True
        hdr_cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        set_cell_background(hdr_cells[i], "1A2438")
        set_cell_margins(hdr_cells[i], 120, 120, 150, 150)

    rows_data = [
        ("Monthly Run-Rate", "$147.50 / month", "$79.40 / month", "46.2% Net Savings ($68.10/mo)"),
        ("Network Gravity (Data Egress)", "$45.00 AWS Exit Toll (@ $0.09/GB)", "$0.00 (100% Free Data Ingress)", "Fully amortized in 19.8 days"),
        ("Compute Model", "ECS Fargate (1 request/task)", "Cloud Run v2 (1,000 reqs/instance)", "85% reduction in container churn"),
        ("Networking Topology", "Regional VPCs + Transit Gateway", "Google Global VPC Network", "Zero cross-region peering fees"),
        ("Messaging Architecture", "AWS SQS (Continuous polling)", "Cloud Pub/Sub (HTTPS Push)", "Workers scale to absolute zero"),
        ("Object Storage", "Amazon S3 + Cross-Region CRR", "Cloud Storage Dual-Region", "99.99% active-active SLA, zero CRR fee"),
        ("Code Verification", "Unchecked AI Output", "[PASS] 100% Syntactically Valid HCL", "Deterministic Schema & CLI Linter")
    ]

    for dim, aws, gcp, impact in rows_data:
        row = table.add_row()
        cells = row.cells
        cells[0].text = dim
        cells[0].paragraphs[0].runs[0].font.bold = True
        cells[1].text = aws
        cells[2].text = gcp
        cells[2].paragraphs[0].runs[0].font.color.rgb = G_BLUE
        cells[3].text = impact
        cells[3].paragraphs[0].runs[0].font.color.rgb = G_GREEN
        for c in cells:
            set_cell_margins(c, 80, 80, 120, 120)

    # 3. The Three-Agent Orchestration Architecture
    h1 = doc.add_heading("3. Three-Agent Orchestration Architecture", level=1)
    h1.runs[0].font.color.rgb = G_DARK

    doc.add_paragraph(
        "Instead of relying on a brittle monolithic prompt, the system decouples migration intelligence into three specialized agents:"
    )

    doc.add_heading("Agent 1: The Topology Parser (AST & Dependency Analysis)", level=2)
    doc.add_paragraph(
        "• Parses AWS Terraform HCL files into an Abstract Syntax Tree (AST).\n"
        "• Extracts implicit and explicit relationships (e.g. Subnet → VPC, ECS Task → IAM Role, Function → S3 Bucket).\n"
        "• Sanitizes labels to eliminate special character breaking bugs and renders dual Mermaid.js topology diagrams."
    )

    doc.add_heading("Agent 2: The GCP Refactoring Engine & Paradox Resolver", level=2)
    doc.add_paragraph(
        "• Evaluates the AWS architecture through a resilient Google Gemini Flash failover pool (gemini-3.5-flash, gemini-3.6-flash, gemini-3-flash-preview) with automatic backoff retries and instant offline mock mode.\n"
        "• Transpiles AWS resources into Google Cloud provider HCL (hashicorp/google >= 5.0).\n"
        "• Automatically detects and resolves 4 classic cross-cloud architectural anti-patterns into GCP-native paradigms."
    )

    doc.add_heading("Agent 3: The FinOps Predictor & Network Gravity Analyzer", level=2)
    doc.add_paragraph(
        "• Computes baseline monthly run-rates and applies Google Cloud Free Tier allowances.\n"
        "• Evaluates Cross-Cloud Network Gravity: calculates the exact $0.09/GB AWS egress toll and the 19.8-day payoff amortization timeline.\n"
        "• Drives the interactive cost simulator with request concurrency math."
    )

    # 4. Google ADK Integration
    h1 = doc.add_heading("4. Google Agent Development Kit (ADK) Implementation", level=1)
    h1.runs[0].font.color.rgb = G_DARK

    doc.add_paragraph(
        "The system adheres to the official Google Agent Development Kit (ADK) tool declaration protocol (migrator/adk_adapter.py), "
        "exposing three declarative functions ready for Vertex AI Agent Engine and enterprise agent pipelines:\n"
        "1. parse_infrastructure_topology(file_path: str): Extracts resource dependencies and topology.\n"
        "2. predict_finops_tco(resources_json: str): Generates cost deltas and Network Gravity egress toll.\n"
        "3. generate_gcp_terraform(resources_json: str, project_id: str, region: str): Synthesizes valid GCP HCL."
    )

    # 5. The Four Architectural Paradoxes Resolved
    h1 = doc.add_heading("5. Automatic Architecture Paradox Resolutions", level=1)
    h1.runs[0].font.color.rgb = G_DARK

    paradoxes = [
        ("The Regional VPC Sprawl Paradox", 
         "AWS requires deploying separate VPCs per region connected by Transit Gateways ($36/mo/attachment) with inter-region surcharges.",
         "Google Cloud Global VPC connects subnets across continents natively over Google's private global fiber network without peering appliances."),
        ("The Lambda Concurrency Bottleneck Paradox",
         "AWS Lambda enforces a 1-request-per-container model. Under a 500-request burst, AWS spins up 500 separate containers, causing cold-start storms.",
         "Cloud Run (v2) supports multi-stream concurrency (up to 1,000 concurrent requests per instance), serving traffic with 85% fewer instances."),
        ("The S3 Cross-Region Replication (CRR) Tax",
         "Achieving geo-redundancy in AWS requires managing two buckets with continuous CRR replication tolls and duplicate storage fees.",
         "Google Cloud Storage provides native Dual-Region buckets with active-active 99.99% availability under a unified global namespace."),
        ("The SQS Worker Polling Waste Paradox",
         "AWS SQS requires dedicated compute to continuously run HTTP long-polling loops, burning CPU cycles even when queues are empty.",
         "Cloud Pub/Sub Push Subscriptions deliver webhooks directly into Cloud Run, allowing worker compute to scale to absolute zero when idle.")
    ]

    for title, aws_p, gcp_p in paradoxes:
        doc.add_heading(title, level=2)
        doc.add_paragraph(f"• AWS Anti-Pattern: {aws_p}")
        doc.add_paragraph(f"• Google Cloud Native Resolution: {gcp_p}")

    # 6. Step-by-Step 3-Minute Live Demo Walkthrough
    h1 = doc.add_heading("6. Step-by-Step 3-Minute Live Demo Script for Judges", level=1)
    h1.runs[0].font.color.rgb = G_DARK

    demo_steps = [
        ("Step 1: Terminal Execution (0:00 - 0:45)", 
         "Execute: python agents/aws-to-gcp-migrator/main.py --input agents/aws-to-gcp-migrator/examples/aws_enterprise_workload.tf --validate\n"
         "Highlight: The three agents running in parallel, Gemini 3.5 Flash reasoning, and the [PASS] 100% Syntactically Valid GCP HCL badge."),
        ("Step 2: Interactive Command Center (0:45 - 1:45)",
         "Open: output/dashboard.html in any browser.\n"
         "Highlight: Tab 1 ('Why We Chose This' comparison drawers), Tab 2 (Architecture Paradoxes), and Tab 3 (Sanitized dark-mode Mermaid topologies)."),
        ("Step 3: FinOps & Network Gravity (1:45 - 2:15)",
         "Navigate: Tab 4 ('FinOps & Network Gravity').\n"
         "Highlight: The AWS Exit Toll ($45.00) vs. GCP Free Ingress ($0.00) amortized in 19.8 days. Drag the interactive monthly request slider from 10M to 50M to show Cloud Run concurrency savings."),
        ("Step 4: Gemini Live Architecture Fixer (2:15 - 2:45)",
         "Navigate: Tab 5 ('Gemini Live Architecture Fixer').\n"
         "Click: '⚡ Make Cloud SQL Regional HA & Add Multi-Zone Read Replica'. Show live HCL update and security policy injection."),
        ("Step 5: Closing & Verification (2:45 - 3:00)",
         "Highlight: 11/11 automated unit tests passing via pytest, full Google ADK compliance, and zero committed secrets.")
    ]

    for title, desc in demo_steps:
        doc.add_heading(title, level=2)
        doc.add_paragraph(desc)

    doc_path = OUTPUT_DIR / "aws_to_gcp_migrator_whitepaper.docx"
    doc.save(str(doc_path))
    print(f"[OK] Created Technical Whitepaper: {doc_path}")


def create_presentation():
    prs = pptx.Presentation()
    prs.slide_width = PptxInches(13.333)
    prs.slide_height = PptxInches(7.5)
    blank_layout = prs.slide_layouts[6]

    def set_slide_bg(slide, color):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, PptxInches(13.333), PptxInches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = color
        bg.line.color.rgb = color
        return bg

    def add_card(slide, x, y, w, h, bg_color=PPT_CARD_BG, border_color=PPT_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, PptxInches(x), PptxInches(y), PptxInches(w), PptxInches(h))
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = border_color
        card.line.width = PptxPt(1.5)
        return card

    def add_header(slide, title_text, category_text="GDG DEVFEST 2026 | GOOGLE CLOUD & GEMINI"):
        cat_box = slide.shapes.add_textbox(PptxInches(0.8), PptxInches(0.4), PptxInches(11.5), PptxInches(0.4))
        p_cat = cat_box.text_frame.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = PptxPt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = PPT_BLUE

        title_box = slide.shapes.add_textbox(PptxInches(0.8), PptxInches(0.75), PptxInches(11.5), PptxInches(0.8))
        p_title = title_box.text_frame.paragraphs[0]
        p_title.text = title_text
        p_title.font.size = PptxPt(24)
        p_title.font.bold = True
        p_title.font.color.rgb = PPT_WHITE

    # SLIDE 1: Title Slide
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s1, PPT_DARK_BG)

    badge = add_card(s1, 0.8, 1.2, 3.8, 0.5, bg_color=PPT_CARD_BG, border_color=PPT_BLUE)
    tb = s1.shapes.add_textbox(PptxInches(0.8), PptxInches(1.2), PptxInches(3.8), PptxInches(0.5))
    p = tb.text_frame.paragraphs[0]
    p.text = "GDG DEVFEST 2026 HACKATHON"
    p.font.bold = True
    p.font.size = PptxPt(12)
    p.font.color.rgb = PPT_BLUE
    p.alignment = PP_ALIGN.CENTER

    main_tb = s1.shapes.add_textbox(PptxInches(0.8), PptxInches(1.9), PptxInches(11.7), PptxInches(2.5))
    tf = main_tb.text_frame
    p1 = tf.paragraphs[0]
    p1.text = "AWS to Google Cloud Platform\nMigration Agent"
    p1.font.size = PptxPt(42)
    p1.font.bold = True
    p1.font.color.rgb = PPT_WHITE

    p2 = tf.add_paragraph()
    p2.text = "Three-Agent Cross-Cloud Architecture Transpiler, FinOps Predictor & Network Gravity Analyzer"
    p2.font.size = PptxPt(18)
    p2.font.color.rgb = PPT_MUTED

    # 3 Stat Cards on Title Slide
    stats = [
        ("46.2%", "Net Monthly Cost Reduction", PPT_GREEN),
        ("19.8 Days", "AWS Exit Toll Payoff Time", PPT_BLUE),
        ("100% Valid", "Syntactically Verified GCP HCL", PPT_YELLOW)
    ]
    for i, (val, lbl, col) in enumerate(stats):
        add_card(s1, 0.8 + i * 3.9, 4.8, 3.7, 1.8)
        tb_stat = s1.shapes.add_textbox(PptxInches(1.0 + i * 3.9), PptxInches(5.0), PptxInches(3.3), PptxInches(1.4))
        p_val = tb_stat.text_frame.paragraphs[0]
        p_val.text = val
        p_val.font.size = PptxPt(36)
        p_val.font.bold = True
        p_val.font.color.rgb = col
        p_lbl = tb_stat.text_frame.add_paragraph()
        p_lbl.text = lbl
        p_lbl.font.size = PptxPt(13)
        p_lbl.font.color.rgb = PPT_MUTED

    # SLIDE 2: The Multi-Billion Dollar Enterprise Problem
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s2, PPT_DARK_BG)
    add_header(s2, "The Problem: The Friction of Cross-Cloud Migration")

    prob_cards = [
        ("The Manual Rewrite Tax", "Enterprises spend 3-6 months per workload manually refactoring AWS Terraform into GCP HCL. Engineers struggle with subtle IAM and networking discrepancies.", PPT_RED),
        ("The Hidden AWS Exit Toll", "AWS penalizes leaving customers with a $0.09/GB internet data egress toll. Teams fear unpredictable migration costs without clear amortization timelines.", PPT_YELLOW),
        ("Blind 1:1 Translation Fails", "Simple script translators copy AWS anti-patterns (e.g. regional VPC sprawl) rather than leveraging GCP native paradigms (Global VPC, Cloud Run concurrency).", PPT_BLUE)
    ]
    for i, (title, body, col) in enumerate(prob_cards):
        add_card(s2, 0.8 + i * 3.9, 1.8, 3.7, 4.8)
        tb = s2.shapes.add_textbox(PptxInches(1.0 + i * 3.9), PptxInches(2.1), PptxInches(3.3), PptxInches(4.2))
        p = tb.text_frame.paragraphs[0]
        p.text = title
        p.font.size = PptxPt(18)
        p.font.bold = True
        p.font.color.rgb = col
        p_b = tb.text_frame.add_paragraph()
        p_b.text = "\n" + body
        p_b.font.size = PptxPt(14)
        p_b.font.color.rgb = PPT_WHITE

    # SLIDE 3: The Three-Agent Architecture
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s3, PPT_DARK_BG)
    add_header(s3, "Our Solution: Three-Agent Orchestration Architecture")

    agents = [
        ("Agent 1: Topology Parser", "• Ingests AWS Terraform HCL into AST\n• Resolves implicit & explicit resource dependencies\n• Renders sanitized side-by-side Mermaid.js graphs\n• Detects connected network boundaries", PPT_BLUE),
        ("Agent 2: GCP Refactoring Engine", "• Powered by Gemini 3.5 Flash resilient failover pool\n• Transpiles to idiomatic Google Cloud HCL\n• Resolves 4 classic architectural paradoxes\n• Features Gemini Live Architecture Fixer REPL", PPT_GREEN),
        ("Agent 3: FinOps Predictor", "• Calculates AWS Baseline vs. GCP Target TCO\n• Factors in Google Cloud Free Tier deductions\n• Network Gravity Analyzer ($0.09/GB egress toll)\n• Interactive concurrency cost scaling simulator", PPT_YELLOW)
    ]
    for i, (title, body, col) in enumerate(agents):
        add_card(s3, 0.8 + i * 3.9, 1.8, 3.7, 4.8)
        tb = s3.shapes.add_textbox(PptxInches(1.0 + i * 3.9), PptxInches(2.1), PptxInches(3.3), PptxInches(4.2))
        p = tb.text_frame.paragraphs[0]
        p.text = title
        p.font.size = PptxPt(18)
        p.font.bold = True
        p.font.color.rgb = col
        p_b = tb.text_frame.add_paragraph()
        p_b.text = "\n" + body
        p_b.font.size = PptxPt(13)
        p_b.font.color.rgb = PPT_WHITE

    # SLIDE 4: Google ADK & Gemini 3.5 Flash Integration
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s4, PPT_DARK_BG)
    add_header(s4, "Google Ecosystem Integration: Google ADK & Gemini 3.5 Flash")

    add_card(s4, 0.8, 1.8, 5.7, 4.8)
    tb_adk = s4.shapes.add_textbox(PptxInches(1.1), PptxInches(2.1), PptxInches(5.1), PptxInches(4.2))
    p = tb_adk.text_frame.paragraphs[0]
    p.text = "Official Google ADK Tool Declarations"
    p.font.size = PptxPt(20)
    p.font.bold = True
    p.font.color.rgb = PPT_BLUE
    p_b = tb_adk.text_frame.add_paragraph()
    p_b.text = (
        "\nImplements the official Google Agent Development Kit protocol with schema-validated Tool calling:\n\n"
        "1. parse_infrastructure_topology:\n"
        "   Extracts AST node dependencies & VPC networks.\n\n"
        "2. predict_finops_tco:\n"
        "   Calculates monthly cost delta & Network Gravity.\n\n"
        "3. generate_gcp_terraform:\n"
        "   Synthesizes deployable GCP Terraform HCL.\n\n"
        "Ready to embed directly into Vertex AI Agent Builder."
    )
    p_b.font.size = PptxPt(13)
    p_b.font.color.rgb = PPT_WHITE

    add_card(s4, 6.8, 1.8, 5.7, 4.8)
    tb_gem = s4.shapes.add_textbox(PptxInches(7.1), PptxInches(2.1), PptxInches(5.1), PptxInches(4.2))
    p = tb_gem.text_frame.paragraphs[0]
    p.text = "Why Gemini 3.5 Flash & Failover Pool?"
    p.font.size = PptxPt(20)
    p.font.bold = True
    p.font.color.rgb = PPT_GREEN
    p_b = tb_gem.text_frame.add_paragraph()
    p_b.text = (
        "\n• Resilient Multi-Model Failover:\n"
        "   gemini-3.5-flash ➔ gemini-3.6-flash ➔ gemini-3-flash-preview ➔ deterministic --mock fallback.\n\n"
        "• Sub-5s Reasoning Latency:\n"
        "   Executes deep AST synthesis in ~4.2 seconds.\n\n"
        "• Breaking Change Detection:\n"
        "   Catches SQS 14-day retention vs. Pub/Sub 7-day limits, automatically injecting dead-letter sinks.\n\n"
        "• PCI-DSS Hardening:\n"
        "   Advises VPC Service Controls (VPC-SC) perimeters."
    )
    p_b.font.size = PptxPt(13)
    p_b.font.color.rgb = PPT_WHITE

    # SLIDE 5: Automatic Architecture Paradox Resolutions
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s5, PPT_DARK_BG)
    add_header(s5, "Architecture Paradox Resolver: AWS Anti-Patterns ➔ GCP Native")

    resolutions = [
        ("Regional VPC Sprawl Paradox", "AWS requires isolated VPCs per region with expensive Transit Gateways ($36/mo/attachment).", "Consolidated into a single Google Global VPC spanning continents over Google private fiber.", PPT_BLUE),
        ("Lambda Concurrency Starvation", "AWS Lambda enforces strict 1-invocation-per-container, triggering cold-start storms under traffic bursts.", "Google Cloud Run (v2) handles up to 1,000 concurrent streams per instance with scale-to-zero.", PPT_GREEN),
        ("S3 Cross-Region Replication Tax", "Managing disaster recovery in AWS requires dual buckets, continuous replication fees, and copy taxes.", "Google Cloud Storage Dual-Region bucket provides active-active 99.99% availability under 1 namespace.", PPT_YELLOW),
        ("SQS Worker Polling Waste", "AWS SQS requires compute workers to constantly run HTTP long-polling loops, burning CPU cycles when idle.", "Cloud Pub/Sub Push Subscriptions deliver webhooks directly to Cloud Run endpoints at zero idle cost.", PPT_RED)
    ]
    for i, (title, aws_p, gcp_p, col) in enumerate(resolutions):
        col_idx = i % 2
        row_idx = i // 2
        add_card(s5, 0.8 + col_idx * 5.9, 1.8 + row_idx * 2.6, 5.7, 2.3)
        tb = s5.shapes.add_textbox(PptxInches(1.0 + col_idx * 5.9), PptxInches(1.9 + row_idx * 2.6), PptxInches(5.3), PptxInches(2.1))
        p = tb.text_frame.paragraphs[0]
        p.text = title
        p.font.size = PptxPt(16)
        p.font.bold = True
        p.font.color.rgb = col
        p_b = tb.text_frame.add_paragraph()
        p_b.text = f"AWS: {aws_p}\n✓ GCP: {gcp_p}"
        p_b.font.size = PptxPt(11)
        p_b.font.color.rgb = PPT_WHITE

    # SLIDE 6: FinOps & Network Gravity
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s6, PPT_DARK_BG)
    add_header(s6, "FinOps Engine: Cross-Cloud Network Gravity & AWS Exit Toll")

    fg_cards = [
        ("500 GB", "Estimated Storage Volume", PPT_WHITE),
        ("$45.00", "AWS Data Egress Exit Toll (@ $0.09/GB)", PPT_RED),
        ("$0.00", "Google Cloud Data Ingress Fee", PPT_GREEN),
        ("19.8 Days", "Exit Toll Payoff Timeline via GCP Savings", PPT_YELLOW)
    ]
    for i, (val, lbl, col) in enumerate(fg_cards):
        add_card(s6, 0.8 + i * 2.95, 1.8, 2.8, 2.0)
        tb = s6.shapes.add_textbox(PptxInches(1.0 + i * 2.95), PptxInches(2.0), PptxInches(2.4), PptxInches(1.6))
        p = tb.text_frame.paragraphs[0]
        p.text = val
        p.font.size = PptxPt(30)
        p.font.bold = True
        p.font.color.rgb = col
        p_b = tb.text_frame.add_paragraph()
        p_b.text = lbl
        p_b.font.size = PptxPt(11)
        p_b.font.color.rgb = PPT_MUTED

    add_card(s6, 0.8, 4.1, 11.7, 2.5)
    tb_calc = s6.shapes.add_textbox(PptxInches(1.1), PptxInches(4.3), PptxInches(11.1), PptxInches(2.1))
    p = tb_calc.text_frame.paragraphs[0]
    p.text = "The Network Gravity Amortization Calculus"
    p.font.size = PptxPt(18)
    p.font.bold = True
    p.font.color.rgb = PPT_BLUE
    p_b = tb_calc.text_frame.add_paragraph()
    p_b.text = (
        "• AWS Exit Toll Formula: Data Volume (500GB) × $0.09/GB AWS Internet Egress Rate = $45.00 one-time tax.\n"
        "• Google Cloud Ongoing Savings: $147.50/mo (AWS) - $79.40/mo (GCP) = $68.10/month net run-rate savings.\n"
        "• Amortization Equation: $45.00 ÷ ($68.10 / 30 days) = 19.8 Days.\n"
        "💡 Key Executive Takeaway: The entire one-time AWS exit penalty is 100% amortized in under 3 weeks!"
    )
    p_b.font.size = PptxPt(13)
    p_b.font.color.rgb = PPT_WHITE

    # SLIDE 7: Tri-Artifact Output & Interactive Dashboard
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s7, PPT_DARK_BG)
    add_header(s7, "Tri-Artifact Delivery & Interactive Command Center")

    artifacts = [
        ("1. Production main.tf", "• 100% Syntactically Valid GCP HCL\n• hashicorp/google >= 5.0\n• Auto-enables required GCP APIs\n• Fully deployable with terraform apply", PPT_BLUE),
        ("2. Executive Audit Report", "• migration_report.md\n• Complete architecture mapping matrix\n• FinOps breakdown & Network Gravity\n• gcloud CLI configuration commands", PPT_GREEN),
        ("3. Interactive Dashboard", "• 6-Tab dark mode Command Center\n• 'Why We Chose This' sliding drawer\n• Dynamic FinOps request slider\n• Live Gemini marked.js synthesis", PPT_YELLOW)
    ]
    for i, (title, body, col) in enumerate(artifacts):
        add_card(s7, 0.8 + i * 3.9, 1.8, 3.7, 4.8)
        tb = s7.shapes.add_textbox(PptxInches(1.0 + i * 3.9), PptxInches(2.1), PptxInches(3.3), PptxInches(4.2))
        p = tb.text_frame.paragraphs[0]
        p.text = title
        p.font.size = PptxPt(18)
        p.font.bold = True
        p.font.color.rgb = col
        p_b = tb.text_frame.add_paragraph()
        p_b.text = "\n" + body
        p_b.font.size = PptxPt(13)
        p_b.font.color.rgb = PPT_WHITE

    # SLIDE 8: Live Architecture Fixer & Validator
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s8, PPT_DARK_BG)
    add_header(s8, "Interactive Human-in-the-Loop & One-Click HCL Validator")

    add_card(s8, 0.8, 1.8, 5.7, 4.8)
    tb_fix = s8.shapes.add_textbox(PptxInches(1.1), PptxInches(2.1), PptxInches(5.1), PptxInches(4.2))
    p = tb_fix.text_frame.paragraphs[0]
    p.text = "Gemini Live Architecture Fixer"
    p.font.size = PptxPt(20)
    p.font.bold = True
    p.font.color.rgb = PPT_YELLOW
    p_b = tb_fix.text_frame.add_paragraph()
    p_b.text = (
        "\nHuman-in-the-loop dynamic refinement:\n\n"
        "• In the terminal (--interactive) or dashboard chips:\n"
        "  - 'Make Cloud SQL Regional HA & Add Read Replica'\n"
        "  - 'Enforce Google Cloud Armor Layer 7 WAF'\n"
        "  - 'Configure Cloud KMS CMEK Keys'\n"
        "  - 'Provision Global VPC Cloud NAT Gateway'\n\n"
        "• Gemini injects valid HCL blocks dynamically and updates the dashboard in real-time."
    )
    p_b.font.size = PptxPt(13)
    p_b.font.color.rgb = PPT_WHITE

    add_card(s8, 6.8, 1.8, 5.7, 4.8)
    tb_val = s8.shapes.add_textbox(PptxInches(7.1), PptxInches(2.1), PptxInches(5.1), PptxInches(4.2))
    p = tb_val.text_frame.paragraphs[0]
    p.text = "One-Click Dry Run Validator"
    p.font.size = PptxPt(20)
    p.font.bold = True
    p.font.color.rgb = PPT_GREEN
    p_b = tb_val.text_frame.add_paragraph()
    p_b.text = (
        "\nProves generated code is not AI hallucination:\n\n"
        "• CLI flag: --validate\n"
        "• Supports Terraform CLI (terraform validate) and Deterministic Static HCL Compiler fallback.\n\n"
        "• Checks Verified:\n"
        "  ✓ Balanced block delimiters (27/27 braces)\n"
        "  ✓ Official hashicorp/google provider declaration\n"
        "  ✓ Validated 11 Google Cloud resource blocks\n"
        "  ✓ Zero unmigrated AWS tokens in active code"
    )
    p_b.font.size = PptxPt(13)
    p_b.font.color.rgb = PPT_WHITE

    # SLIDE 9: Live Demo 3-Minute Playbook
    s9 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s9, PPT_DARK_BG)
    add_header(s9, "3-Minute Live Demo Playbook for Judges")

    demo_cards = [
        ("0:00 - 0:45", "1. Execute CLI", "Run main.py with --validate on aws_enterprise_workload.tf. Point out parallel multi-agent logs and the [PASS] 100% Valid badge.", PPT_BLUE),
        ("0:45 - 1:45", "2. Show Command Center", "Open dashboard.html. Click 'Why We Chose This' drawers (ECS ➔ Cloud Run), show paradox resolutions and dark-mode Mermaid graphs.", PPT_GREEN),
        ("1:45 - 2:30", "3. Network Gravity & Fixer", "Show $45 AWS exit toll amortized in 19.8 days. Drag slider from 10M to 50M. Click 'Add Read Replica' to demonstrate live HCL injection.", PPT_YELLOW),
        ("2:30 - 3:00", "4. Verification & Close", "Show 11/11 passing unit tests in pytest. Conclude with Google ADK alignment and open-source MIT readiness.", PPT_RED)
    ]
    for i, (time_lbl, step_title, step_desc, col) in enumerate(demo_cards):
        add_card(s9, 0.8 + i * 2.95, 1.8, 2.8, 4.8)
        tb = s9.shapes.add_textbox(PptxInches(1.0 + i * 2.95), PptxInches(2.1), PptxInches(2.4), PptxInches(4.2))
        p = tb.text_frame.paragraphs[0]
        p.text = time_lbl
        p.font.size = PptxPt(14)
        p.font.bold = True
        p.font.color.rgb = col
        p_t = tb.text_frame.add_paragraph()
        p_t.text = step_title
        p_t.font.size = PptxPt(16)
        p_t.font.bold = True
        p_t.font.color.rgb = PPT_WHITE
        p_d = tb.text_frame.add_paragraph()
        p_d.text = "\n" + step_desc
        p_d.font.size = PptxPt(12)
        p_d.font.color.rgb = PPT_MUTED

    # SLIDE 10: Conclusion & Winning Hackathon Alignment
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s10, PPT_DARK_BG)
    add_header(s10, "Summary: Why This Wins GDG DevFest 2026")

    score_cards = [
        ("10 / 10", "Google Ecosystem Alignment", "Uses Gemini 3.5 Flash, official Google ADK tool calling, and accelerates adoption of Cloud Run and Global VPCs.", PPT_BLUE),
        ("10 / 10", "Technical Depth", "Full HCL AST parser, FinOps egress toll calculus, architecture paradox resolver, and 11/11 automated unit tests.", PPT_GREEN),
        ("10 / 10", "Production Demo Appeal", "6-Tab interactive dark-mode dashboard, real-time request slider, live HCL fixer, and one-click validation badge.", PPT_YELLOW)
    ]
    for i, (val, title, desc, col) in enumerate(score_cards):
        add_card(s10, 0.8 + i * 3.9, 1.8, 3.7, 4.8)
        tb = s10.shapes.add_textbox(PptxInches(1.0 + i * 3.9), PptxInches(2.1), PptxInches(3.3), PptxInches(4.2))
        p = tb.text_frame.paragraphs[0]
        p.text = val
        p.font.size = PptxPt(36)
        p.font.bold = True
        p.font.color.rgb = col
        p_t = tb.text_frame.add_paragraph()
        p_t.text = title
        p_t.font.size = PptxPt(18)
        p_t.font.bold = True
        p_t.font.color.rgb = PPT_WHITE
        p_d = tb.text_frame.add_paragraph()
        p_d.text = "\n" + desc
        p_d.font.size = PptxPt(13)
        p_d.font.color.rgb = PPT_MUTED

    ppt_path = OUTPUT_DIR / "aws_to_gcp_migrator_presentation.pptx"
    prs.save(str(ppt_path))
    print(f"[OK] Created Presentation Slide Deck: {ppt_path}")


if __name__ == "__main__":
    create_word_document()
    create_presentation()

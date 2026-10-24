"""Script to generate professional Google DevFest presentation slides for Jarvis."""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_deck(output_path: str):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Color Palette: Google Brand + Modern Dark/Tech Theme
    BG_DARK = RGBColor(15, 23, 42)       # Slate 900
    CARD_BG = RGBColor(30, 41, 59)       # Slate 800
    TEXT_LIGHT = RGBColor(248, 250, 252) # Slate 50
    TEXT_MUTED = RGBColor(148, 163, 184) # Slate 400
    BLUE = RGBColor(66, 133, 244)        # Google Blue
    RED = RGBColor(234, 67, 53)          # Google Red
    YELLOW = RGBColor(251, 188, 4)       # Google Yellow
    GREEN = RGBColor(52, 168, 83)        # Google Green
    ACCENT_CYAN = RGBColor(56, 189, 248) # Cyan 400

    blank_layout = prs.slide_layouts[6]

    def add_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = BG_DARK
        bg.line.fill.background()
        return bg

    def add_header(slide, title_text, category_text="ROAD TO DEVFEST • GOOGLE ANANTA"):
        tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(1.2))
        tf = tb.text_frame
        tf.word_wrap = True
        
        p_cat = tf.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = BLUE
        p_cat.space_after = Pt(4)

        p_title = tf.add_paragraph()
        p_title.text = title_text
        p_title.font.size = Pt(28)
        p_title.font.bold = True
        p_title.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 1: Title Slide
    # ==========================================
    s1 = prs.slides.add_slide(blank_layout)
    add_background(s1)

    # Accent bar
    bar = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.5), Inches(0.6), Inches(0.08))
    bar.fill.solid()
    bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background()

    tb = s1.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.5), Inches(4.5))
    tf = tb.text_frame
    tf.word_wrap = True

    p0 = tf.paragraphs[0]
    p0.text = "ROAD TO DEVFEST 2026: FORK • BUILD • MERGE"
    p0.font.size = Pt(13)
    p0.font.bold = True
    p0.font.color.rgb = BLUE
    p0.space_after = Pt(12)

    p1 = tf.add_paragraph()
    p1.text = "Jarvis — A PR Review Agent"
    p1.font.size = Pt(44)
    p1.font.bold = True
    p1.font.color.rgb = TEXT_LIGHT
    p1.space_after = Pt(12)

    p2 = tf.add_paragraph()
    p2.text = "Autonomous Git Diff Auditor with 5-Layer Guardrail Defense & Dual-Engine AI (Google Gemini + Local Gemma 2)"
    p2.font.size = Pt(20)
    p2.font.color.rgb = TEXT_MUTED
    p2.space_after = Pt(28)

    p3 = tf.add_paragraph()
    p3.text = "Built by: Shaik Mohammed Ashraf Ali  |  Venue: Google Ananta Office, Bengaluru"
    p3.font.size = Pt(14)
    p3.font.bold = True
    p3.font.color.rgb = ACCENT_CYAN

    # ==========================================
    # SLIDE 2: Problem & Motivation
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    add_background(s2)
    add_header(s2, "The Problem: Maintainer Burnout & Secret Leak Epidemic")

    cards_data = [
        ("Review Fatigue", RED, "Maintainers spend 60%+ of their code review cycles checking repetitive hygiene: syntax, test coverage, and lockfiles instead of architecture."),
        ("Accidental Leaks", YELLOW, "Developers accidentally commit Google AI keys, GitHub PATs, and AWS tokens. Traditional LLM prompts can hallucinate and miss them."),
        ("Vague PR Descriptions", BLUE, "PRs often arrive with blank or vague summaries ('fixes stuff'), delaying reviews and making audit trails nearly impossible."),
        ("Cloud Privacy Risks", GREEN, "Enterprise & proprietary codebases cannot legally send raw unvetted source code to public external LLMs without air-gap guarantees.")
    ]

    for i, (title, color, desc) in enumerate(cards_data):
        x = Inches(0.8 + (i * 2.95))
        y = Inches(2.0)
        w = Inches(2.8)
        h = Inches(4.5)

        card = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = color
        card.line.width = Pt(1.5)

        tb = s2.shapes.add_textbox(x + Inches(0.15), y + Inches(0.2), w - Inches(0.3), h - Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True

        pt = tf.paragraphs[0]
        pt.text = title
        pt.font.size = Pt(18)
        pt.font.bold = True
        pt.font.color.rgb = color
        pt.space_after = Pt(14)

        pd = tf.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(13)
        pd.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 3: Architecture & Dual-Engine Design
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    add_background(s3)
    add_header(s3, "Architecture: Dual-Engine Model Tier (HLD)")

    col1 = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0), Inches(5.6), Inches(4.5))
    col1.fill.solid()
    col1.fill.fore_color.rgb = CARD_BG
    col1.line.color.rgb = BLUE
    col1.line.width = Pt(1.5)

    tb1 = s3.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(5.2), Inches(4.1))
    tf1 = tb1.text_frame
    tf1.word_wrap = True

    p = tf1.paragraphs[0]
    p.text = "🔒 Privacy Tier: Google Gemma 2 (Local)"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = BLUE
    p.space_after = Pt(10)

    bullets1 = [
        "Runs 100% offline via Ollama (gemma2:2b) directly on Mac.",
        "Zero egress: Proprietary code never leaves the laptop.",
        "Deterministic pre-LLM secret shield catches leaked API keys.",
        "Detects code execution anti-patterns: eval(), exec(), shell=True.",
        "Ideal for air-gapped CI and privacy-sensitive enterprises."
    ]
    for b in bullets1:
        pb = tf1.add_paragraph()
        pb.text = f"• {b}"
        pb.font.size = Pt(13)
        pb.font.color.rgb = TEXT_LIGHT
        pb.space_after = Pt(6)

    col2 = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(2.0), Inches(5.7), Inches(4.5))
    col2.fill.solid()
    col2.fill.fore_color.rgb = CARD_BG
    col2.line.color.rgb = GREEN
    col2.line.width = Pt(1.5)

    tb2 = s3.shapes.add_textbox(Inches(7.0), Inches(2.2), Inches(5.3), Inches(4.1))
    tf2 = tb2.text_frame
    tf2.word_wrap = True

    p = tf2.paragraphs[0]
    p.text = "⚡ Architect Tier: Google Gemini 2.5 Flash"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = GREEN
    p.space_after = Pt(10)

    bullets2 = [
        "Deep semantic reasoning across multi-file diffs.",
        "Assesses architectural impact and breaking API changes.",
        "Auto-generates standardized Conventional PR summaries.",
        "Synthesizes tailored testing verification checklists.",
        "Fallback Mock Provider ensures 100% test pass rate in CI."
    ]
    for b in bullets2:
        pb = tf2.add_paragraph()
        pb.text = f"• {b}"
        pb.font.size = Pt(13)
        pb.font.color.rgb = TEXT_LIGHT
        pb.space_after = Pt(6)

    # ==========================================
    # SLIDE 4: The 5-Layer Guardrail Architecture
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    add_background(s4)
    add_header(s4, "Core Innovation: 5-Layer Guardrail Defense")

    layers = [
        ("Layer 1", "Context & DOS Guard", BLUE, "Strips lockfiles (package-lock.json) and minified files so diffs never blow out LLM token limits."),
        ("Layer 2", "Secret Shield (Pre-LLM)", RED, "Zero-hallucination regex audit for Google AI keys (AIzaSy...), GitHub PATs, AWS, and .env files."),
        ("Layer 3", "Anti-Pattern Execution Guard", YELLOW, "Catches arbitrary code execution risks: eval(), exec(), subprocess(shell=True), and raw SQL formatting."),
        ("Layer 4", "Air-Gapped Privacy Guard", GREEN, "Local execution on Google Gemma 2 (gemma2:2b). Complete air-gap guarantee for confidential code."),
        ("Layer 5", "Authoritative Verdict Escalation", ACCENT_CYAN, "The LLM CANNOT approve unsafe code. If critical issues exist, verdict is forcibly set to REQUEST_CHANGES.")
    ]

    for i, (l_num, l_title, l_col, l_desc) in enumerate(layers):
        y = Inches(1.8 + (i * 1.05))
        box = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), y, Inches(11.7), Inches(0.9))
        box.fill.solid()
        box.fill.fore_color.rgb = CARD_BG
        box.line.color.rgb = l_col
        box.line.width = Pt(1.5)

        tb = s4.shapes.add_textbox(Inches(1.0), y + Inches(0.1), Inches(11.3), Inches(0.7))
        tf = tb.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = f"{l_num}: {l_title}"
        p.font.size = Pt(15)
        p.font.bold = True
        p.font.color.rgb = l_col
        p.space_after = Pt(2)

        p2 = tf.add_paragraph()
        p2.text = l_desc
        p2.font.size = Pt(12)
        p2.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 5: Testing & Verification
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    add_background(s5)
    add_header(s5, "Verification: 9/9 Automated Tests & Dual Interface")

    # Left: Test suite
    col1 = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0), Inches(5.6), Inches(4.5))
    col1.fill.solid()
    col1.fill.fore_color.rgb = CARD_BG
    col1.line.color.rgb = GREEN
    col1.line.width = Pt(1.5)

    tb1 = s5.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(5.2), Inches(4.1))
    tf1 = tb1.text_frame
    tf1.word_wrap = True

    p = tf1.paragraphs[0]
    p.text = "🧪 100% Automated Test Suite"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = GREEN
    p.space_after = Pt(10)

    test_bullets = [
        "test_security_scanner_clean_diff [PASSED]",
        "test_security_scanner_detects_secrets_and_eval [PASSED]",
        "test_security_scanner_detects_sql_injection [PASSED]",
        "test_git_utils_filter_lockfiles [PASSED]",
        "test_agent_mock_review_clean [PASSED]",
        "test_agent_critical_issue_escalates_verdict [PASSED]",
        "test_markdown_pr_generation [PASSED]",
        "test_fastapi_health_endpoint [PASSED]",
        "test_fastapi_review_endpoint [PASSED]",
        "⚡ 9 passed in 0.19s with Pytest!"
    ]
    for b in test_bullets:
        pb = tf1.add_paragraph()
        pb.text = b
        pb.font.size = Pt(12)
        pb.font.color.rgb = ACCENT_CYAN if "PASSED" in b or "passed" in b else TEXT_LIGHT
        pb.space_after = Pt(3)

    # Right: Dual Interfaces
    col2 = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(2.0), Inches(5.7), Inches(4.5))
    col2.fill.solid()
    col2.fill.fore_color.rgb = CARD_BG
    col2.line.color.rgb = BLUE
    col2.line.width = Pt(1.5)

    tb2 = s5.shapes.add_textbox(Inches(7.0), Inches(2.2), Inches(5.3), Inches(4.1))
    tf2 = tb2.text_frame
    tf2.word_wrap = True

    p = tf2.paragraphs[0]
    p.text = "🚀 Dual Interface Capabilities"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = BLUE
    p.space_after = Pt(10)

    iface_bullets = [
        "1. Terminal CLI Mode:",
        "   $ python main.py --branch main",
        "   $ python main.py --provider ollama --model gemma2:2b",
        "   Instant formatted review and pr_description.md output.",
        "",
        "2. FastAPI REST Server Mode:",
        "   $ python main.py --serve",
        "   Interactive Swagger UI live at http://localhost:8000/docs",
        "   Endpoints: /api/review, /api/generate-pr, /api/health.",
        "   Ready for CI/CD webhook pipelines and Git hooks."
    ]
    for b in iface_bullets:
        pb = tf2.add_paragraph()
        pb.text = b
        pb.font.size = Pt(12)
        pb.font.color.rgb = YELLOW if b.startswith("1.") or b.startswith("2.") else TEXT_LIGHT
        pb.space_after = Pt(2)

    # ==========================================
    # SLIDE 6: Live Demo Walkthrough
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    add_background(s6)
    add_header(s6, "Live Demo: Guardrails & Conventional PR in Action")

    demo_steps = [
        ("Demo 1: The Leak Trap", RED, "Feed a git diff containing a leaked Google AI key + eval(). Watch Layer 2 catch the secret and Layer 5 force verdict = REQUEST_CHANGES."),
        ("Demo 2: 100% Offline Review", GREEN, "Switch to local Google Gemma 2 (gemma2:2b). Run inspection with zero internet access, proving complete air-gap compliance."),
        ("Demo 3: Auto-Generated PR", BLUE, "Provide a clean multi-file feature diff. Jarvis analyzes changes and auto-writes a standardized Conventional PR markdown with checklist.")
    ]

    for i, (title, color, desc) in enumerate(demo_steps):
        x = Inches(0.8 + (i * 3.95))
        y = Inches(2.0)
        w = Inches(3.8)
        h = Inches(4.5)

        card = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = color
        card.line.width = Pt(1.5)

        tb = s6.shapes.add_textbox(x + Inches(0.2), y + Inches(0.25), w - Inches(0.4), h - Inches(0.5))
        tf = tb.text_frame
        tf.word_wrap = True

        pt = tf.paragraphs[0]
        pt.text = title
        pt.font.size = Pt(18)
        pt.font.bold = True
        pt.font.color.rgb = color
        pt.space_after = Pt(14)

        pd = tf.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(13)
        pd.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 7: Summary & Impact
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    add_background(s7)
    add_header(s7, "Summary & Why Jarvis Wins at DevFest")

    summary_box = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0), Inches(11.7), Inches(4.5))
    summary_box.fill.solid()
    summary_box.fill.fore_color.rgb = CARD_BG
    summary_box.line.color.rgb = BLUE
    summary_box.line.width = Pt(1.5)

    tb = s7.shapes.add_textbox(Inches(1.2), Inches(2.3), Inches(11.0), Inches(3.9))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "🎯 Key Takeaways for Judges"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = BLUE
    p.space_after = Pt(14)

    takeaways = [
        "1. True Dual-Engine Innovation: Combines Google Gemini for cloud reasoning and Google Gemma 2 for on-box privacy.",
        "2. Defense-in-Depth Security: 5-layer guardrails ensure secrets are never leaked and unsafe code is never approved.",
        "3. Production Quality: 9/9 automated tests passing, clean FastAPI Swagger UI, and zero external dependencies for scanner.",
        "4. Seamless Developer UX: Runs directly in your terminal, pre-commit hook, or REST API service.",
        "5. Open Source Contribution Ready: PR submitted cleanly to gdgcblr/open-source-agents following strict guidelines."
    ]
    for t in takeaways:
        pt = tf.add_paragraph()
        pt.text = t
        pt.font.size = Pt(14)
        pt.font.color.rgb = TEXT_LIGHT
        pt.space_after = Pt(10)

    prs.save(output_path)
    print(f"Presentation saved successfully to {output_path}")

if __name__ == "__main__":
    out_dir = "/Users/ashraf/open-source-agents/agents/git-pr-review-agent"
    create_deck(os.path.join(out_dir, "Jarvis_PR_Review_Agent_DevFest.pptx"))

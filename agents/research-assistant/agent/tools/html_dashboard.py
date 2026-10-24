"""Interactive Executive HTML Dashboard generator for Research Dossiers."""

import html
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _simple_markdown_to_html(md_text: str) -> str:
    """Converts common Markdown constructs into clean, semantic HTML."""
    lines = md_text.strip().split("\n")
    html_lines = []
    in_list = False
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Code block toggle
        if stripped.startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = stripped[3:].strip()
                html_lines.append(f'<pre><code class="language-{html.escape(lang)}">')
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(html.escape(line))
            continue

        # Close list if not in a bullet
        if in_list and not (stripped.startswith("- ") or stripped.startswith("* ")):
            html_lines.append("</ul>")
            in_list = False

        # Blank lines
        if not stripped:
            continue

        # Headings
        if stripped.startswith("### "):
            text = html.escape(stripped[4:].strip())
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.lower()).strip("-")
            html_lines.append(f'<h3 id="{anchor}">{text}</h3>')
        elif stripped.startswith("## "):
            text = html.escape(stripped[3:].strip())
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.lower()).strip("-")
            html_lines.append(f'<h2 id="{anchor}">{text}</h2>')
        elif stripped.startswith("# "):
            text = html.escape(stripped[2:].strip())
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.lower()).strip("-")
            html_lines.append(f'<h1 id="{anchor}">{text}</h1>')
        # Blockquotes
        elif stripped.startswith("> "):
            quote_text = html.escape(stripped[2:].strip())
            html_lines.append(f"<blockquote>{quote_text}</blockquote>")
        # Bullet list items
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append('<ul class="report-list">')
                in_list = True
            item_text = html.escape(stripped[2:].strip())
            # Replace markdown bold and links inside list
            item_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", item_text)
            item_text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', item_text)
            html_lines.append(f"<li>{item_text}</li>")
        # Regular paragraph
        else:
            p_text = html.escape(stripped)
            p_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", p_text)
            p_text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', p_text)
            html_lines.append(f"<p>{p_text}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_code_block:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


def _extract_toc(md_text: str) -> List[Dict[str, str]]:
    """Extracts table of contents items from H2 and H3 markdown headers."""
    toc = []
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.lower()).strip("-")
            toc.append({"title": title, "anchor": anchor, "level": "h2"})
        elif stripped.startswith("### "):
            title = stripped[4:].strip()
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.lower()).strip("-")
            toc.append({"title": title, "anchor": anchor, "level": "h3"})
    return toc


def _extract_evidence_cards(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extracts structured source cards from observation history."""
    cards = []
    for h in history:
        if h.get("role") == "observation":
            content = h.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("href"):
                        cards.append({
                            "type": "search",
                            "title": item.get("title", "Search Finding"),
                            "url": item.get("href", ""),
                            "snippet": item.get("body", "")
                        })
            elif isinstance(content, dict) and content.get("url"):
                cards.append({
                    "type": "scrape",
                    "title": content.get("title", "Scraped Webpage"),
                    "url": content.get("url", ""),
                    "snippet": content.get("content", "")[:300] + "...",
                    "chars": content.get("char_count", len(content.get("content", "")))
                })
    return cards


def generate_html_dashboard(
    topic: str,
    markdown_content: str,
    metrics: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Renders a self-contained, enterprise interactive HTML dashboard."""
    metrics = metrics or {}
    history = history or []

    run_id = metrics.get("run_id", "local-run")
    duration = metrics.get("duration_seconds", 0.0)
    steps_taken = metrics.get("steps_taken", 0)
    searches = metrics.get("searches_performed", 0)
    pages_scraped = metrics.get("pages_scraped", 0)
    total_chars = metrics.get("total_chars_analyzed", 0)
    mock_mode = metrics.get("mock_mode", False)

    rendered_body = _simple_markdown_to_html(markdown_content)
    toc_items = _extract_toc(markdown_content)
    evidence_cards = _extract_evidence_cards(history)

    # Build TOC HTML
    toc_html = ""
    for item in toc_items:
        indent_class = "toc-sub" if item["level"] == "h3" else "toc-main"
        toc_html += f'<a href="#{item["anchor"]}" class="toc-link {indent_class}">{html.escape(item["title"])}</a>\n'

    # Build Evidence HTML
    evidence_html = ""
    for i, card in enumerate(evidence_cards, 1):
        type_badge = "Web Search" if card["type"] == "search" else "Deep Scrape"
        badge_color = "badge-blue" if card["type"] == "search" else "badge-purple"
        chars_info = f' • <span class="card-chars">{card.get("chars", 0):,} chars</span>' if card.get("chars") else ""
        evidence_html += f"""
        <div class="evidence-card">
            <div class="card-header">
                <span class="card-badge {badge_color}">{type_badge}</span>
                <span class="card-num">#{i}</span>
                <a href="{html.escape(card['url'])}" target="_blank" rel="noopener" class="card-title">
                    {html.escape(card['title'])}
                </a>
                {chars_info}
            </div>
            <p class="card-snippet">{html.escape(card['snippet'])}</p>
            <div class="card-footer">
                <a href="{html.escape(card['url'])}" target="_blank" rel="noopener" class="card-link">
                    🔗 {html.escape(card['url'])}
                </a>
            </div>
        </div>
        """

    safe_topic = html.escape(topic)
    raw_md_json = json.dumps(markdown_content).replace("<", "\\u003c").replace(">", "\\u003e")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Dossier: {safe_topic}</title>
    <style>
        :root {{
            --bg-primary: #0b0f19;
            --bg-secondary: #111827;
            --bg-card: rgba(30, 41, 59, 0.7);
            --border-color: rgba(255, 255, 255, 0.1);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-cyan: #06b6d4;
            --accent-purple: #a855f7;
            --accent-green: #10b981;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 24px;
        }}
        .container {{ max-width: 1280px; margin: 0 auto; }}
        /* Header Hero */
        .hero {{
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.4), rgba(88, 28, 135, 0.3));
            border: 1px solid var(--border-color);
            backdrop-filter: blur(12px);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
        }}
        .hero-badge {{
            display: inline-block;
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-blue);
            font-size: 0.8rem;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 9999px;
            margin-bottom: 12px;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}
        .hero h1 {{ font-size: 2.2rem; font-weight: 800; margin-bottom: 8px; color: #ffffff; }}
        .hero-meta {{ color: var(--text-secondary); font-size: 0.95rem; }}
        /* Action Bar */
        .action-bar {{ display: flex; gap: 12px; margin-top: 20px; }}
        .btn {{
            cursor: pointer;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }}
        .btn:hover {{ background: rgba(255, 255, 255, 0.15); transform: translateY(-1px); }}
        .btn-primary {{ background: #2563eb; border-color: #3b82f6; }}
        .btn-primary:hover {{ background: #1d4ed8; }}
        /* Metrics Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            backdrop-filter: blur(8px);
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        }}
        .metric-val {{ font-size: 1.8rem; font-weight: 700; color: var(--accent-blue); }}
        .metric-label {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-top: 4px; }}
        /* Layout */
        .main-layout {{ display: grid; grid-template-columns: 280px 1fr; gap: 24px; }}
        @media (max-width: 900px) {{ .main-layout {{ grid-template-columns: 1fr; }} }}
        /* TOC Sidebar */
        .toc-sidebar {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            height: fit-content;
            position: sticky;
            top: 24px;
        }}
        .toc-sidebar h4 {{ font-size: 0.85rem; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 12px; }}
        .toc-link {{ display: block; color: var(--text-secondary); text-decoration: none; padding: 6px 0; font-size: 0.9rem; transition: color 0.15s; }}
        .toc-link:hover {{ color: var(--accent-blue); }}
        .toc-sub {{ padding-left: 14px; font-size: 0.85rem; }}
        /* Content Area */
        .content-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 32px;
            backdrop-filter: blur(8px);
        }}
        .content-card h1, .content-card h2, .content-card h3 {{ color: #ffffff; margin-top: 28px; margin-bottom: 12px; }}
        .content-card h1:first-child, .content-card h2:first-child {{ margin-top: 0; }}
        .content-card p {{ margin-bottom: 16px; color: #cbd5e1; }}
        .content-card blockquote {{
            border-left: 4px solid var(--accent-blue);
            background: rgba(56, 189, 248, 0.08);
            padding: 12px 16px;
            margin-bottom: 16px;
            border-radius: 0 8px 8px 0;
            color: #e2e8f0;
        }}
        .content-card ul.report-list {{ margin-left: 20px; margin-bottom: 16px; color: #cbd5e1; }}
        .content-card ul.report-list li {{ margin-bottom: 6px; }}
        .content-card a {{ color: var(--accent-blue); text-decoration: none; }}
        .content-card a:hover {{ text-decoration: underline; }}
        /* Evidence Section */
        .evidence-section {{ margin-top: 40px; padding-top: 24px; border-top: 1px solid var(--border-color); }}
        .evidence-card {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 12px;
        }}
        .card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }}
        .card-badge {{ font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; }}
        .badge-blue {{ background: rgba(56, 189, 248, 0.2); color: var(--accent-blue); }}
        .badge-purple {{ background: rgba(168, 85, 247, 0.2); color: var(--accent-purple); }}
        .card-num {{ color: var(--text-secondary); font-size: 0.8rem; }}
        .card-title {{ font-weight: 600; color: #ffffff; text-decoration: none; }}
        .card-title:hover {{ color: var(--accent-blue); }}
        .card-snippet {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 8px; }}
        .card-link {{ font-size: 0.8rem; color: var(--accent-cyan); text-decoration: none; word-break: break-all; }}
        /* Toast Notification */
        .toast {{
            position: fixed; bottom: 24px; right: 24px;
            background: #10b981; color: #ffffff;
            padding: 10px 20px; border-radius: 8px;
            font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            display: none; animation: fadeIn 0.2s ease-in-out;
        }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        /* Print Styles */
        @media print {{
            body {{ background: #ffffff; color: #000000; padding: 0; }}
            .hero, .metric-card, .content-card, .evidence-card {{ background: none; border: 1px solid #ccc; color: #000; }}
            .action-bar, .toc-sidebar {{ display: none !important; }}
            .main-layout {{ display: block; }}
            .hero h1, .content-card h1, .content-card h2, .content-card h3 {{ color: #000000; }}
            .metric-val {{ color: #000000; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Hero Header -->
        <header class="hero">
            <span class="hero-badge">Google DevFest 2026 • Autonomous Research Assistant</span>
            <h1>{safe_topic}</h1>
            <p class="hero-meta">
                Run ID: <code>{html.escape(run_id)}</code> • Mode: <strong>{"Offline Mock" if mock_mode else "Live Gemini 2.5 Flash"}</strong>
            </p>
            <div class="action-bar">
                <button class="btn btn-primary" onclick="copyMarkdown()">📋 Copy Markdown Dossier</button>
                <button class="btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
            </div>
        </header>

        <!-- Metrics Grid -->
        <section class="metrics-grid">
            <div class="metric-card">
                <div class="metric-val">{duration}s</div>
                <div class="metric-label">Execution Time</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{steps_taken}</div>
                <div class="metric-label">Agent Turns</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{searches}</div>
                <div class="metric-label">Web Searches</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{pages_scraped}</div>
                <div class="metric-label">Deep Scrapes</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{total_chars:,}</div>
                <div class="metric-label">Chars Analyzed</div>
            </div>
        </section>

        <!-- Main Layout -->
        <div class="main-layout">
            <!-- Sidebar Table of Contents -->
            <aside class="toc-sidebar">
                <h4>Table of Contents</h4>
                {toc_html or '<p style="color:#64748b; font-size:0.85rem;">No sections parsed</p>'}
                <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-color);">
                    <h4>Sources & Audit</h4>
                    <a href="#evidence-section" class="toc-link">🔍 Evidence Explorer ({len(evidence_cards)})</a>
                </div>
            </aside>

            <!-- Main Content Card -->
            <main class="content-card">
                {rendered_body}

                <!-- Evidence Explorer -->
                <section id="evidence-section" class="evidence-section">
                    <h2>🔍 Evidence Explorer & Grounding Audit</h2>
                    <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 20px;">
                        The claims in this dossier are cross-referenced from the following {len(evidence_cards)} retrieved online sources:
                    </p>
                    {evidence_html or '<p style="color:#64748b;">No external sources tracked in this run.</p>'}
                </section>
            </main>
        </div>
    </div>

    <div id="toast" class="toast">✓ Markdown copied to clipboard!</div>

    <script>
        const rawMarkdown = {raw_md_json};

        function copyMarkdown() {{
            navigator.clipboard.writeText(rawMarkdown).then(() => {{
                const toast = document.getElementById('toast');
                toast.style.display = 'block';
                setTimeout(() => {{ toast.style.display = 'none'; }}, 2500);
            }}).catch(err => {{
                alert('Could not copy markdown to clipboard: ' + err);
            }});
        }}
    </script>
</body>
</html>
"""

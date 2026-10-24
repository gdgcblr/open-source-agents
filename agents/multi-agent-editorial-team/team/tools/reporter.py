"""Publication and reporting exporter for Multi-Agent Editorial Team."""

import datetime
import html
import json
import logging
import os
import re
from typing import Any, Dict, Optional

from ..state import TeamState

logger = logging.getLogger(__name__)


def sanitize_slug(topic: str) -> str:
    """Sanitizes topic into safe filesystem slug."""
    clean = re.sub(r"[^a-zA-Z0-9_\-]+", "_", topic.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean[:50] or "untitled_article"


def _markdown_to_html(md_text: str) -> str:
    """Converts basic markdown into semantic HTML elements."""
    lines = md_text.strip().split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{html.escape(stripped[4:].strip())}</h3>")
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
        elif stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item_text = html.escape(stripped[2:].strip())
            item_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", item_text)
            item_text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', item_text)
            html_lines.append(f"<li>{item_text}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            p_text = html.escape(stripped)
            p_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", p_text)
            p_text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', p_text)
            html_lines.append(f"<p>{p_text}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def generate_editorial_dashboard(state: TeamState) -> str:
    """Generates a self-contained, interactive HTML dashboard showing draft evolution and agent trace."""
    metrics = state.metrics
    run_id = metrics.run_id if metrics else "run-id"
    duration = metrics.duration_seconds if metrics else 0.0
    final_score = metrics.final_score if metrics else (state.latest_verdict.score if state.latest_verdict else 85)
    revisions = metrics.revision_count if metrics else state.revision_turns
    evidence_count = len(state.evidence)
    messages_count = len(state.messages)

    # Build agent messages timeline
    messages_html = ""
    for msg in state.messages:
        badge_class = f"role-{msg.sender.value}"
        messages_html += f"""
        <div class="msg-card">
            <div class="msg-header">
                <span class="role-badge {badge_class}">{msg.sender.value.upper()}</span>
                <span class="msg-arrow">➔</span>
                <span class="role-badge role-{msg.recipient.value}">{msg.recipient.value.upper()}</span>
                <span class="msg-turn">Turn {msg.turn}</span>
                <span class="msg-time">{msg.timestamp.strftime('%H:%M:%S')}</span>
            </div>
            <p class="msg-content">{html.escape(msg.content)}</p>
        </div>
        """

    # Build verdict cards
    verdicts_html = ""
    for i, v in enumerate(state.verdict_history, 1):
        status_color = "status-approved" if v.status.value == "APPROVED" else "status-revise"
        critiques_list = "".join([f"<li><strong>[{c.aspect}]</strong> ({c.severity}): {html.escape(c.feedback)}</li>" for c in v.critiques])
        verdicts_html += f"""
        <div class="verdict-card {status_color}">
            <div class="verdict-header">
                <span class="verdict-title">Review Gate v{i}</span>
                <span class="verdict-score">{v.score} / 100</span>
                <span class="verdict-status">{v.status.value}</span>
            </div>
            <p class="verdict-summary">{html.escape(v.summary)}</p>
            {f'<ul class="verdict-critiques">{critiques_list}</ul>' if critiques_list else ''}
        </div>
        """

    # Build draft tabs content
    draft_tabs_html = ""
    for idx, draft in enumerate(state.draft_history, 1):
        draft_tabs_html += f"""
        <div class="draft-pane {'active' if idx == len(state.draft_history) else ''}" id="draft-v{idx}">
            <div class="draft-badge-row">
                <span class="draft-tag">Draft Revision v{idx}</span>
                {f'<span class="draft-tag-final">Final Published Version</span>' if idx == len(state.draft_history) else ''}
            </div>
            <div class="article-body">
                {_markdown_to_html(draft)}
            </div>
        </div>
        """

    tab_buttons_html = ""
    for idx in range(1, len(state.draft_history) + 1):
        active_class = "active" if idx == len(state.draft_history) else ""
        tab_buttons_html += f'<button class="tab-btn {active_class}" onclick="switchTab({idx})">Draft v{idx}</button>'

    safe_topic = html.escape(state.topic)
    raw_final_md = json.dumps(state.current_draft).replace("<", "\\u003c").replace(">", "\\u003e")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Editorial Report: {safe_topic}</title>
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-card: rgba(23, 32, 54, 0.7);
            --border-color: rgba(255, 255, 255, 0.12);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-green: #10b981;
            --accent-purple: #c084fc;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            padding: 24px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1280px; margin: 0 auto; }}
        /* Hero */
        .hero {{
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.45), rgba(126, 34, 206, 0.35));
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
            backdrop-filter: blur(12px);
        }}
        .hero-badge {{
            display: inline-block;
            background: rgba(56, 189, 248, 0.2);
            color: var(--accent-blue);
            font-size: 0.8rem;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 9999px;
            margin-bottom: 12px;
            letter-spacing: 0.05em;
        }}
        .hero h1 {{ font-size: 2.2rem; margin-bottom: 8px; font-weight: 800; }}
        .hero-meta {{ color: var(--text-secondary); font-size: 0.9rem; }}
        .action-row {{ display: flex; gap: 12px; margin-top: 18px; }}
        .btn {{
            cursor: pointer;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: #fff;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            transition: all 0.2s;
        }}
        .btn:hover {{ background: rgba(255, 255, 255, 0.15); }}
        .btn-primary {{ background: #2563eb; border-color: #3b82f6; }}
        /* Metrics */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        }}
        .metric-val {{ font-size: 1.8rem; font-weight: 800; color: var(--accent-blue); }}
        .metric-label {{ font-size: 0.75rem; text-transform: uppercase; color: var(--text-secondary); margin-top: 4px; }}
        /* Multi-Agent DAG Visualizer */
        .pipeline-dag {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .pipeline-dag h3 {{ font-size: 0.95rem; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 16px; }}
        .dag-flow {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }}
        .dag-node {{
            flex: 1; min-width: 140px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }}
        .dag-node-title {{ font-size: 0.85rem; font-weight: 700; color: #fff; }}
        .dag-node-desc {{ font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px; }}
        .dag-arrow {{ font-size: 1.2rem; color: var(--accent-blue); }}
        /* Layout */
        .main-grid {{ display: grid; grid-template-columns: 1fr 340px; gap: 24px; }}
        @media (max-width: 1000px) {{ .main-grid {{ grid-template-columns: 1fr; }} }}
        /* Drafts Tabs */
        .content-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 28px;
        }}
        .tab-bar {{ display: flex; gap: 8px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 20px; }}
        .tab-btn {{
            background: transparent; border: none; color: var(--text-secondary);
            font-size: 0.9rem; font-weight: 600; cursor: pointer; padding: 6px 14px;
            border-radius: 6px;
        }}
        .tab-btn.active {{ background: #2563eb; color: #fff; }}
        .draft-pane {{ display: none; }}
        .draft-pane.active {{ display: block; }}
        .draft-badge-row {{ display: flex; gap: 8px; margin-bottom: 18px; }}
        .draft-tag {{ background: rgba(255, 255, 255, 0.1); font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; color: var(--text-secondary); }}
        .draft-tag-final {{ background: rgba(16, 185, 129, 0.2); color: var(--accent-green); font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
        .article-body h1, .article-body h2, .article-body h3 {{ color: #ffffff; margin-top: 24px; margin-bottom: 10px; }}
        .article-body h1:first-child {{ margin-top: 0; }}
        .article-body p {{ margin-bottom: 14px; color: #cbd5e1; }}
        .article-body ul {{ margin-left: 20px; margin-bottom: 14px; color: #cbd5e1; }}
        .article-body li {{ margin-bottom: 4px; }}
        .article-body a {{ color: var(--accent-blue); text-decoration: none; }}
        .article-body a:hover {{ text-decoration: underline; }}
        /* Sidebar: Audit & Verdicts */
        .sidebar {{ display: flex; flex-direction: column; gap: 20px; }}
        .side-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }}
        .side-card h3 {{ font-size: 0.9rem; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 14px; }}
        /* Verdict Cards */
        .verdict-card {{
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 12px;
            border: 1px solid var(--border-color);
            background: rgba(15, 23, 42, 0.6);
        }}
        .verdict-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .verdict-score {{ font-weight: 800; color: var(--accent-blue); }}
        .status-approved .verdict-status {{ color: var(--accent-green); font-weight: 700; font-size: 0.8rem; }}
        .status-revise .verdict-status {{ color: var(--accent-amber); font-weight: 700; font-size: 0.8rem; }}
        .verdict-summary {{ font-size: 0.85rem; color: #cbd5e1; margin-bottom: 8px; }}
        .verdict-critiques {{ font-size: 0.8rem; color: #94a3b8; margin-left: 16px; }}
        /* Messages */
        .msg-card {{
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 8px;
            font-size: 0.85rem;
        }}
        .msg-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; flex-wrap: wrap; }}
        .role-badge {{ font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; }}
        .role-planner {{ background: rgba(56, 189, 248, 0.2); color: var(--accent-blue); }}
        .role-researcher {{ background: rgba(168, 85, 247, 0.2); color: var(--accent-purple); }}
        .role-writer {{ background: rgba(16, 185, 129, 0.2); color: var(--accent-green); }}
        .role-reviewer {{ background: rgba(245, 158, 11, 0.2); color: var(--accent-amber); }}
        .role-orchestrator {{ background: rgba(244, 63, 94, 0.2); color: var(--accent-rose); }}
        .msg-arrow {{ color: var(--text-secondary); font-size: 0.75rem; }}
        .msg-time {{ margin-left: auto; color: #64748b; font-size: 0.7rem; }}
        .msg-content {{ color: #cbd5e1; font-size: 0.8rem; }}
        /* Toast */
        .toast {{
            position: fixed; bottom: 24px; right: 24px;
            background: #10b981; color: #fff;
            padding: 10px 18px; border-radius: 8px;
            font-weight: 600; display: none;
        }}
        @media print {{
            body {{ background: #fff; color: #000; padding: 0; }}
            .hero, .content-card, .metric-card {{ background: none; border: 1px solid #ccc; color: #000; }}
            .action-row, .tab-bar, .sidebar, .pipeline-dag {{ display: none !important; }}
            .main-grid {{ display: block; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Hero Header -->
        <header class="hero">
            <span class="hero-badge">Multi-Agent Collaborative Pipeline • DevFest 2026</span>
            <h1>{safe_topic}</h1>
            <p class="hero-meta">
                Run ID: <code>{html.escape(run_id)}</code> • Status: <strong>{'APPROVED' if state.is_approved else 'Best-Effort Published'}</strong>
            </p>
            <div class="action-row">
                <button class="btn btn-primary" onclick="copyFinalMarkdown()">📋 Copy Final Article</button>
                <button class="btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
            </div>
        </header>

        <!-- Metrics Grid -->
        <section class="metrics-grid">
            <div class="metric-card">
                <div class="metric-val">{final_score}/100</div>
                <div class="metric-label">Quality Score</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{revisions}</div>
                <div class="metric-label">Revisions Made</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{evidence_count}</div>
                <div class="metric-label">Verified Sources</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{messages_count}</div>
                <div class="metric-label">A2A Messages</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{duration}s</div>
                <div class="metric-label">Execution Time</div>
            </div>
        </section>

        <!-- Pipeline DAG Visualizer -->
        <section class="pipeline-dag">
            <h3>Collaborative Agent Flow</h3>
            <div class="dag-flow">
                <div class="dag-node">
                    <div class="dag-node-title">1. Planner Agent</div>
                    <div class="dag-node-desc">Blueprint & Outlines</div>
                </div>
                <span class="dag-arrow">➔</span>
                <div class="dag-node">
                    <div class="dag-node-title">2. Researcher Agent</div>
                    <div class="dag-node-desc">Live DuckDuckGo Evidence</div>
                </div>
                <span class="dag-arrow">➔</span>
                <div class="dag-node">
                    <div class="dag-node-title">3. Writer Agent</div>
                    <div class="dag-node-desc">Prose Synthesis (v1)</div>
                </div>
                <span class="dag-arrow">➔</span>
                <div class="dag-node">
                    <div class="dag-node-title">4. Reviewer Agent</div>
                    <div class="dag-node-desc">Rubric Quality Gate</div>
                </div>
                <span class="dag-arrow">➔</span>
                <div class="dag-node">
                    <div class="dag-node-title">5. Revision Loop</div>
                    <div class="dag-node-desc">{revisions} Revisions Applied</div>
                </div>
            </div>
        </section>

        <!-- Main Workspace Grid -->
        <div class="main-grid">
            <!-- Article & Draft Evolution -->
            <main class="content-card">
                <div class="tab-bar">
                    {tab_buttons_html}
                </div>
                {draft_tabs_html}
            </main>

            <!-- Sidebar Audit Trail -->
            <aside class="sidebar">
                <!-- Reviewer Quality Gate -->
                <div class="side-card">
                    <h3>Reviewer Audits ({len(state.verdict_history)})</h3>
                    {verdicts_html}
                </div>

                <!-- Inter-Agent Communication Trace -->
                <div class="side-card">
                    <h3>Inter-Agent Trace ({len(state.messages)})</h3>
                    <div style="max-height: 480px; overflow-y: auto;">
                        {messages_html}
                    </div>
                </div>
            </aside>
        </div>
    </div>

    <div id="toast" class="toast">✓ Final article copied to clipboard!</div>

    <script>
        const finalMarkdown = {raw_final_md};

        function switchTab(idx) {{
            document.querySelectorAll('.tab-btn').forEach((btn, i) => {{
                btn.classList.toggle('active', (i + 1) === idx);
            }});
            document.querySelectorAll('.draft-pane').forEach((pane, i) => {{
                pane.classList.toggle('active', (i + 1) === idx);
            }});
        }}

        function copyFinalMarkdown() {{
            navigator.clipboard.writeText(finalMarkdown).then(() => {{
                const toast = document.getElementById('toast');
                toast.style.display = 'block';
                setTimeout(() => {{ toast.style.display = 'none'; }}, 2500);
            }});
        }}
    </script>
</body>
</html>
"""


def export_publication_artifacts(state: TeamState, output_dir: str = "reports") -> Dict[str, str]:
    """Saves both the final Markdown article and the interactive HTML dashboard with audit history.

    Args:
        state: Completed TeamState object.
        output_dir: Target directory.

    Returns:
        Dictionary containing 'markdown_path' and 'html_path'.
    """
    safe_dir = os.path.abspath(output_dir)
    os.makedirs(safe_dir, exist_ok=True)

    slug = sanitize_slug(state.topic)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(safe_dir, f"editorial_{slug}_{timestamp}.md")
    html_path = os.path.join(safe_dir, f"editorial_{slug}_{timestamp}.html")

    metrics = state.metrics
    score = metrics.final_score if metrics else 85
    duration = metrics.duration_seconds if metrics else 0.0
    revisions = metrics.revision_count if metrics else state.revision_turns
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header = f"""---
topic: "{state.topic.replace('"', '')}"
generated_at: "{now_str}"
agent_pipeline: "open-source-ai / multi-agent-editorial-team"
quality_score: {score}
revisions_applied: {revisions}
duration_seconds: {duration}
evidence_sources_count: {len(state.evidence)}
inter_agent_messages_count: {len(state.messages)}
---

"""
    full_markdown = header + state.current_draft.strip() + "\n"

    # Write Markdown
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_markdown)

    # Write HTML Dashboard
    html_content = generate_editorial_dashboard(state)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Published Markdown article: {md_path}")
    logger.info(f"Published HTML dashboard: {html_path}")

    return {
        "markdown_path": md_path,
        "html_path": html_path
    }

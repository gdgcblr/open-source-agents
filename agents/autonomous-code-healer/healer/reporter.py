"""Interactive HTML Dashboard and Report Generator for Autonomous Code Healer."""

import html
import json
import os
from typing import Any, Dict


def generate_healing_html_dashboard(result: Dict[str, Any], output_path: str = "") -> str:
    """Generates a self-contained, enterprise-grade dark mode HTML dashboard.

    Args:
        result: Dictionary returned by AutonomousCodeHealer.heal().
        output_path: Optional path to save the generated HTML file.

    Returns:
        HTML string representation of the interactive dashboard.
    """
    metrics = result.get("metrics", {})
    status = result.get("status", "unknown")
    run_id = metrics.get("run_id", "N/A")
    target_file = metrics.get("target_file", result.get("file_path", "unknown"))
    filename = os.path.basename(target_file)
    test_cmd = metrics.get("test_command", "pytest")
    duration = metrics.get("duration_seconds", 0.0)
    attempts_made = metrics.get("attempts_made", 0)
    diff_text = result.get("diff", "")
    diff_lines_count = metrics.get("diff_lines_changed", 0)
    mock_mode = metrics.get("mock_mode", False)
    attempts = result.get("attempts", [])
    original_code = result.get("original_code", "")
    healed_code = result.get("healed_code", "")

    status_badge_color = {
        "healed_successfully": "status-success",
        "already_passing": "status-info",
        "rollback_after_failed_attempts": "status-danger",
        "failed_unverified": "status-danger",
    }.get(status, "status-neutral")

    status_label = {
        "healed_successfully": "HEALED & VERIFIED",
        "already_passing": "BASELINE PASSING",
        "rollback_after_failed_attempts": "ROLLED BACK (FAILED)",
        "failed_unverified": "FAILED",
    }.get(status, status.upper())

    # Build Diff HTML Lines
    diff_html_lines = []
    if diff_text:
        for line in diff_text.splitlines():
            escaped = html.escape(line)
            if line.startswith("+++") or line.startswith("---"):
                diff_html_lines.append(f'<div class="diff-line diff-meta">{escaped}</div>')
            elif line.startswith("@@"):
                diff_html_lines.append(f'<div class="diff-line diff-chunk">{escaped}</div>')
            elif line.startswith("+"):
                diff_html_lines.append(f'<div class="diff-line diff-add">{escaped}</div>')
            elif line.startswith("-"):
                diff_html_lines.append(f'<div class="diff-line diff-del">{escaped}</div>')
            else:
                diff_html_lines.append(f'<div class="diff-line diff-ctx">{escaped}</div>')
    else:
        diff_html_lines.append('<div class="diff-empty">No diff generated (baseline already passing or no edits).</div>')

    # Build Attempt Timeline HTML Cards
    attempt_cards_html = []
    for att in attempts:
        num = att.get("attempt_num", 1)
        ast_ok = att.get("ast_safe", False)
        ast_reason = html.escape(att.get("ast_reason", ""))
        test_ok = att.get("test_passed", False)
        exit_code = att.get("exit_code", 0)
        dur = att.get("duration_seconds", 0.0)
        err_snippet = html.escape(att.get("error_snippet", ""))

        ast_badge = '<span class="badge badge-success">AST Passed</span>' if ast_ok else f'<span class="badge badge-danger">AST Blocked</span>'
        test_badge = '<span class="badge badge-success">Test Passed</span>' if test_ok else f'<span class="badge badge-danger">Exit {exit_code}</span>'

        err_block = f'<div class="trace-snippet"><pre>{err_snippet}</pre></div>' if err_snippet else ""

        card = f"""
        <div class="attempt-card {'attempt-pass' if test_ok else 'attempt-fail'}">
            <div class="attempt-header">
                <span class="attempt-title">Cycle #{num}</span>
                <div class="attempt-badges">
                    {ast_badge}
                    {test_badge}
                    <span class="badge badge-neutral">{dur}s</span>
                </div>
            </div>
            <div class="attempt-body">
                <p><strong>AST Audit:</strong> {ast_reason}</p>
                {err_block}
            </div>
        </div>
        """
        attempt_cards_html.append(card)

    if not attempt_cards_html:
        attempt_cards_html.append('<div class="empty-state">No healing attempts required. Tests were already green.</div>')

    # Safe payload JSON (OWASP escaping for script tag)
    payload_json = json.dumps(result, indent=2, default=str)
    safe_payload = payload_json.replace("<", "\\u003c").replace(">", "\\u003e")

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Code Healer Dashboard - {html.escape(filename)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-secondary: #121826;
            --bg-card: rgba(22, 30, 46, 0.75);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-cyan: #38bdf8;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
            --accent-purple: #a855f7;
            --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background: radial-gradient(circle at top right, #1e1b4b, #0a0e17 65%);
            color: var(--text-primary);
            font-family: var(--font-sans);
            min-height: 100vh;
            padding: 32px 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px 32px;
            backdrop-filter: blur(12px);
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .header-title-box h1 {{
            font-size: 24px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .header-title-box p {{
            font-size: 14px;
            color: var(--text-secondary);
            font-family: var(--font-mono);
            margin-top: 4px;
        }}

        .status-badge {{
            padding: 8px 18px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}

        .status-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .status-info {{
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}

        .status-danger {{
            background: rgba(244, 63, 94, 0.15);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.3);
        }}

        .status-neutral {{
            background: rgba(148, 163, 184, 0.15);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }}

        /* Metrics Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}

        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(8px);
        }}

        .metric-label {{
            font-size: 12px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }}

        .metric-value {{
            font-size: 26px;
            font-weight: 700;
            margin-top: 6px;
            color: #fff;
        }}

        .metric-sub {{
            font-size: 12px;
            color: var(--text-secondary);
            font-family: var(--font-mono);
            margin-top: 4px;
        }}

        /* Section Layout */
        .dashboard-content {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 24px;
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            backdrop-filter: blur(12px);
        }}

        .card-header {{
            padding: 16px 24px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .card-title {{
            font-size: 16px;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .card-body {{
            padding: 20px 24px;
        }}

        /* Diff Viewer */
        .diff-viewer {{
            background: #090d16;
            border-radius: 8px;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 13px;
            overflow-x: auto;
            max-height: 480px;
            overflow-y: auto;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .diff-line {{
            white-space: pre-wrap;
            line-height: 1.5;
            padding: 2px 6px;
            border-radius: 3px;
        }}

        .diff-add {{
            background: rgba(16, 185, 129, 0.18);
            color: #6ee7b7;
        }}

        .diff-del {{
            background: rgba(244, 63, 94, 0.18);
            color: #fda4af;
        }}

        .diff-meta {{
            color: #a855f7;
            font-weight: 600;
        }}

        .diff-chunk {{
            color: #38bdf8;
            background: rgba(56, 189, 248, 0.1);
        }}

        .diff-ctx {{
            color: #94a3b8;
        }}

        .diff-empty {{
            color: var(--text-muted);
            font-style: italic;
            padding: 16px;
            text-align: center;
        }}

        /* Attempt Cards */
        .attempts-list {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .attempt-card {{
            border: 1px solid var(--border-color);
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.5);
            padding: 16px;
        }}

        .attempt-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 8px;
        }}

        .attempt-title {{
            font-size: 14px;
            font-weight: 700;
            color: #fff;
        }}

        .attempt-badges {{
            display: flex;
            gap: 8px;
        }}

        .badge {{
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 6px;
            font-family: var(--font-mono);
        }}

        .badge-success {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
        }}

        .badge-danger {{
            background: rgba(244, 63, 94, 0.2);
            color: #fb7185;
        }}

        .badge-neutral {{
            background: rgba(148, 163, 184, 0.2);
            color: #cbd5e1;
        }}

        .attempt-body p {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}

        .trace-snippet {{
            background: #050811;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 10px;
            font-family: var(--font-mono);
            font-size: 12px;
            color: #f87171;
            max-height: 140px;
            overflow-y: auto;
        }}

        /* Code Viewer Tabs */
        .tabs-header {{
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border-color);
            padding: 0 24px;
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 12px 16px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            font-family: var(--font-sans);
            transition: all 0.2s;
        }}

        .tab-btn.active {{
            color: var(--accent-cyan);
            border-bottom-color: var(--accent-cyan);
        }}

        .tab-content {{
            display: none;
            padding: 20px 24px;
        }}

        .tab-content.active {{
            display: block;
        }}

        .code-box {{
            background: #090d16;
            border-radius: 8px;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 13px;
            color: #cbd5e1;
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .footer {{
            text-align: center;
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 40px;
            padding-bottom: 20px;
        }}

        .footer a {{
            color: var(--accent-cyan);
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="header-title-box">
                <h1>Autonomous Code Healer</h1>
                <p>Target: {html.escape(target_file)}</p>
            </div>
            <div>
                <span class="status-badge {status_badge_color}">{status_label}</span>
            </div>
        </header>

        <!-- Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Execution Duration</div>
                <div class="metric-value">{duration}s</div>
                <div class="metric-sub">Run ID: {html.escape(run_id)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Healing Cycles</div>
                <div class="metric-value">{attempts_made}</div>
                <div class="metric-sub">Mode: {"Offline Mock" if mock_mode else "Live Gemini"}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Diff Magnitude</div>
                <div class="metric-value">{diff_lines_count}</div>
                <div class="metric-sub">Lines Changed</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Verification Command</div>
                <div class="metric-value" style="font-size: 16px; font-family: var(--font-mono);">{html.escape(test_cmd)}</div>
                <div class="metric-sub">Sandboxed Subprocess</div>
            </div>
        </div>

        <div class="dashboard-content">
            <!-- Diff View Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>Surgical Code Patch (Unified Diff)</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="diff-viewer">
                        {"".join(diff_html_lines)}
                    </div>
                </div>
            </div>

            <!-- Healing Loop History -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>Autonomous Reasoning & Verification Cycles</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="attempts-list">
                        {"".join(attempt_cards_html)}
                    </div>
                </div>
            </div>

            <!-- Code Comparison Tabs -->
            <div class="card">
                <div class="tabs-header">
                    <button class="tab-btn active" onclick="openTab(event, 'healed-tab')">Healed Code</button>
                    <button class="tab-btn" onclick="openTab(event, 'original-tab')">Original (Broken) Code</button>
                </div>
                <div id="healed-tab" class="tab-content active">
                    <pre class="code-box"><code>{html.escape(healed_code)}</code></pre>
                </div>
                <div id="original-tab" class="tab-content">
                    <pre class="code-box"><code>{html.escape(original_code)}</code></pre>
                </div>
            </div>
        </div>

        <footer class="footer">
            Generated autonomously by <strong>Google DevFest Autonomous Code Healer Agent</strong> | Clean-room verified
        </footer>
    </div>

    <!-- Embedded Raw Data Payload (XSS-safe) -->
    <script id="healer-data-payload" type="application/json">
    {safe_payload}
    </script>

    <script>
        function openTab(evt, tabId) {{
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));
            const btns = document.querySelectorAll('.tab-btn');
            btns.forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }}
    </script>
</body>
</html>
"""

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_template)

    return html_template

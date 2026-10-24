"""Interactive HTML Dashboard and Report Generator for Token Usage and Cost Calculator."""

import html
import json
import os
from typing import Optional
from .models import ComparisonReport


def generate_cost_dashboard_html(report: ComparisonReport, output_path: Optional[str] = None) -> str:
    """Renders a self-contained, enterprise-grade dark mode HTML dashboard for token & cost analytics.

    Args:
        report: ComparisonReport returned by analyze_token_costs().
        output_path: Optional path to save the generated HTML file.

    Returns:
        HTML string representation of the dashboard.
    """
    b = report.breakdown
    p = report.primary_estimate

    max_cost = max([c.total_cost_usd for c in report.comparisons] + [0.000001])

    # Build Comparison Rows
    comp_rows = []
    for comp in report.comparisons:
        is_primary = comp.model_id == p.model_id
        is_cheapest = comp.model_id == report.cheapest_model_id

        badge_txt = ""
        if is_primary:
            badge_txt += ' <span class="badge badge-info">Current</span>'
        if is_cheapest:
            badge_txt += ' <span class="badge badge-success">Best Value</span>'

        bar_pct = min(100.0, max(2.0, (comp.total_cost_usd / max_cost) * 100.0))

        comp_rows.append(f"""
        <tr>
            <td><strong>{html.escape(comp.model_id)}</strong>{badge_txt}</td>
            <td><span class="provider-pill">{html.escape(comp.provider)}</span></td>
            <td>{comp.context_window:,} tokens</td>
            <td>${comp.prompt_cost_usd:.6f}</td>
            <td>${comp.completion_cost_usd:.6f}</td>
            <td class="cost-cell">${comp.total_cost_usd:.6f}</td>
            <td style="width: 140px;">
                <div class="cost-bar-bg">
                    <div class="cost-bar-fill" style="width: {bar_pct}%;"></div>
                </div>
            </td>
        </tr>
        """)

    payload_json = json.dumps(report.model_dump(), indent=2, default=str)
    safe_payload = payload_json.replace("<", "\\u003c").replace(">", "\\u003e")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token Usage &amp; Cost Analytics - {html.escape(report.source_label)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-card: rgba(22, 30, 46, 0.75);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-cyan: #38bdf8;
            --accent-emerald: #10b981;
            --accent-purple: #a855f7;
            --accent-rose: #f43f5e;
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

        .header h1 {{
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .header p {{
            font-size: 13px;
            color: var(--text-secondary);
            font-family: var(--font-mono);
            margin-top: 4px;
        }}

        .format-badge {{
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            font-family: var(--font-mono);
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

        /* Table Card */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            margin-bottom: 24px;
            overflow: hidden;
            backdrop-filter: blur(12px);
        }}

        .card-header {{
            padding: 16px 24px;
            border-bottom: 1px solid var(--border-color);
            font-size: 16px;
            font-weight: 700;
            color: #fff;
        }}

        .card-body {{
            padding: 20px 24px;
            overflow-x: auto;
        }}

        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        .data-table th, .data-table td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}

        .data-table th {{
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
        }}

        .provider-pill {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-secondary);
        }}

        .cost-cell {{
            font-family: var(--font-mono);
            font-weight: 700;
            color: #34d399;
        }}

        .cost-bar-bg {{
            background: rgba(255, 255, 255, 0.08);
            border-radius: 9999px;
            height: 8px;
            overflow: hidden;
        }}

        .cost-bar-fill {{
            background: linear-gradient(90deg, #38bdf8, #10b981);
            height: 100%;
            border-radius: 9999px;
        }}

        .badge {{
            font-size: 10px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            text-transform: uppercase;
            font-family: var(--font-mono);
            margin-left: 6px;
        }}

        .badge-success {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
        }}

        .badge-info {{
            background: rgba(56, 189, 248, 0.2);
            color: #38bdf8;
        }}

        .footer {{
            text-align: center;
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 40px;
            padding-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div>
                <h1>Token Usage &amp; Cost Calculator</h1>
                <p>Analyzed: {html.escape(report.source_label)}</p>
            </div>
            <div>
                <span class="format-badge">Format: {html.escape(report.source_format)}</span>
            </div>
        </header>

        <!-- Key Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total Tokens</div>
                <div class="metric-value">{b.total_tokens:,}</div>
                <div class="metric-sub">{b.total_characters:,} Characters ({b.message_count} msgs)</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Input / Output Ratio</div>
                <div class="metric-value" style="font-size: 20px;">{b.prompt_tokens:,} / {b.completion_tokens:,}</div>
                <div class="metric-sub">Prompt vs Completion Tokens</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Target Model ({html.escape(p.model_id)})</div>
                <div class="metric-value" style="color: #34d399;">${p.total_cost_usd:.6f}</div>
                <div class="metric-sub">${p.prompt_cost_usd:.6f} in / ${p.completion_cost_usd:.6f} out</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Potential Savings</div>
                <div class="metric-value" style="color: #38bdf8;">{report.max_savings_percentage}%</div>
                <div class="metric-sub">Best Value: {html.escape(report.cheapest_model_id)}</div>
            </div>
        </div>

        <!-- Comparison Table -->
        <div class="card">
            <div class="card-header">
                Multi-Provider Model Pricing &amp; Economics Comparison
            </div>
            <div class="card-body">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Model</th>
                            <th>Provider</th>
                            <th>Context Window</th>
                            <th>Prompt Cost</th>
                            <th>Completion Cost</th>
                            <th>Total Cost (USD)</th>
                            <th>Relative Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(comp_rows)}
                    </tbody>
                </table>
            </div>
        </div>

        <footer class="footer">
            Token Usage &amp; Cost Calculator | Google DevFest AI Open Source Agents Toolkit
        </footer>
    </div>

    <!-- JSON Payload -->
    <script id="cost-data-payload" type="application/json">
    {safe_payload}
    </script>
</body>
</html>
"""

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    return html_content

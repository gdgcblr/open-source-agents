"""Interactive HTML Dashboard and Report Generator for Prompt Context Linter."""

import html
import json
import os
from typing import Optional
from .models import LintReport, LintSeverity


def generate_lint_dashboard_html(report: LintReport, output_path: Optional[str] = None) -> str:
    """Renders a self-contained, enterprise glassmorphism HTML dashboard for a LintReport.

    Args:
        report: LintReport returned by PromptLinter.lint().
        output_path: Optional path to write the HTML file.

    Returns:
        HTML string of the dashboard.
    """
    status_label = "LINT PASSED" if report.is_valid else f"LINT FAILED ({report.errors_count} Errors)"
    status_class = "status-success" if report.is_valid else "status-danger"

    # Build Issues HTML Cards
    issues_html = []
    for issue in report.issues:
        sev = issue.severity.value
        badge_cls = {
            "ERROR": "badge-danger",
            "WARNING": "badge-warning",
            "INFO": "badge-info",
        }.get(sev, "badge-neutral")

        line_str = f"Line {issue.line_number}" if issue.line_number else "Global"
        sugg = f"<div class='issue-suggestion'><strong>Suggestion:</strong> {html.escape(issue.suggestion)}</div>" if issue.suggestion else ""

        card = f"""
        <div class="issue-card issue-{sev.lower()}">
            <div class="issue-header">
                <span class="badge {badge_cls}">{sev}</span>
                <span class="issue-rule">{html.escape(issue.rule_id)}</span>
                <span class="issue-line">{line_str}</span>
            </div>
            <div class="issue-message">{html.escape(issue.message)}</div>
            {sugg}
        </div>
        """
        issues_html.append(card)

    if not issues_html:
        issues_html.append('<div class="empty-state">No lint issues found. Template adheres cleanly to prompt engineering best practices!</div>')

    # Build Variables Matrix
    all_vars = sorted(list(set(report.variables_found + report.variables_missing + report.variables_unused)))
    var_rows = []
    for v in all_vars:
        if v in report.variables_missing:
            st = '<span class="badge badge-danger">Missing Value</span>'
        elif v in report.variables_unused:
            st = '<span class="badge badge-warning">Unused in Template</span>'
        else:
            st = '<span class="badge badge-success">Supplied &amp; Bound</span>'
        var_rows.append(f"<tr><td><code>{{{html.escape(v)}}}</code></td><td>{st}</td></tr>")

    var_table = f"""
    <table class="data-table">
        <thead>
            <tr><th>Variable Placeholder</th><th>Status</th></tr>
        </thead>
        <tbody>
            {"".join(var_rows) if var_rows else '<tr><td colspan="2" style="text-align:center;">No variables in template</td></tr>'}
        </tbody>
    </table>
    """

    payload_json = json.dumps(report.model_dump(), indent=2, default=str)
    safe_payload = payload_json.replace("<", "\\u003c").replace(">", "\\u003e")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prompt Linter Dashboard - {html.escape(report.template_name)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
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
            --accent-amber: #f59e0b;
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

        .status-badge {{
            padding: 8px 18px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
        }}

        .status-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .status-danger {{
            background: rgba(244, 63, 94, 0.15);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.3);
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

        /* Content Cards */
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
        }}

        /* Issues List */
        .issues-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .issue-card {{
            border: 1px solid var(--border-color);
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.5);
            padding: 14px 18px;
        }}

        .issue-header {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 6px;
        }}

        .badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            font-family: var(--font-mono);
        }}

        .badge-danger {{
            background: rgba(244, 63, 94, 0.2);
            color: #fb7185;
        }}

        .badge-warning {{
            background: rgba(245, 158, 11, 0.2);
            color: #fbbf24;
        }}

        .badge-info {{
            background: rgba(56, 189, 248, 0.2);
            color: #38bdf8;
        }}

        .badge-success {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
        }}

        .badge-neutral {{
            background: rgba(148, 163, 184, 0.2);
            color: #94a3b8;
        }}

        .issue-rule {{
            font-size: 13px;
            font-weight: 700;
            color: #e2e8f0;
            font-family: var(--font-mono);
        }}

        .issue-line {{
            font-size: 12px;
            color: var(--text-muted);
            font-family: var(--font-mono);
        }}

        .issue-message {{
            font-size: 14px;
            color: var(--text-primary);
        }}

        .issue-suggestion {{
            font-size: 12px;
            color: var(--accent-cyan);
            background: rgba(56, 189, 248, 0.08);
            padding: 6px 10px;
            border-radius: 6px;
            margin-top: 8px;
        }}

        .empty-state {{
            padding: 24px;
            text-align: center;
            color: #34d399;
            font-size: 14px;
        }}

        /* Table */
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        .data-table th, .data-table td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}

        .data-table th {{
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
        }}

        .data-table code {{
            font-family: var(--font-mono);
            color: var(--accent-cyan);
        }}

        /* Code Viewer */
        .code-box {{
            background: #090d16;
            border-radius: 8px;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 13px;
            color: #cbd5e1;
            overflow-x: auto;
            max-height: 400px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            white-space: pre-wrap;
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
                <h1>Prompt Context Linter</h1>
                <p>Template: {html.escape(report.template_name)}</p>
            </div>
            <div>
                <span class="status-badge {status_class}">{status_label}</span>
            </div>
        </header>

        <!-- Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Estimated Tokens</div>
                <div class="metric-value">{report.estimated_token_count}</div>
                <div class="metric-sub">{report.raw_character_count} Characters</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Lint Issues</div>
                <div class="metric-value">{report.total_issues}</div>
                <div class="metric-sub">{report.errors_count} Errors | {report.warnings_count} Warnings</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Variables Bound</div>
                <div class="metric-value">{len(report.variables_found)}</div>
                <div class="metric-sub">{len(report.variables_missing)} Missing | {len(report.variables_unused)} Unused</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Validation Status</div>
                <div class="metric-value" style="font-size: 18px; color: {'#34d399' if report.is_valid else '#fb7185'};">
                    {"VALID SYNTAX" if report.is_valid else "CORRECTIONS REQUIRED"}
                </div>
                <div class="metric-sub">Deterministic Rules Engine</div>
            </div>
        </div>

        <!-- Issues List Card -->
        <div class="card">
            <div class="card-header">Lint Findings &amp; Smell Diagnostic Audit</div>
            <div class="card-body">
                <div class="issues-list">
                    {"".join(issues_html)}
                </div>
            </div>
        </div>

        <!-- Variable Analysis Card -->
        <div class="card">
            <div class="card-header">Template Variable Binding Matrix</div>
            <div class="card-body">
                {var_table}
            </div>
        </div>

        <!-- Output Preview Card -->
        <div class="card">
            <div class="card-header">Interpolated Prompt Preview</div>
            <div class="card-body">
                <pre class="code-box"><code>{html.escape(report.interpolated_preview)}</code></pre>
            </div>
        </div>

        <footer class="footer">
            Prompt Context Linter &amp; Formatter | Google DevFest AI Open Source Agents Toolkit
        </footer>
    </div>

    <!-- JSON Payload -->
    <script id="linter-data-payload" type="application/json">
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

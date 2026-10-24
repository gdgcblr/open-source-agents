import json
from .models import ReviewReport


def generate_html_dashboard(report: ReviewReport) -> str:
    """Generate a sleek, standalone dark-mode interactive HTML report dashboard."""
    verdict_color = {
        "APPROVED": "#10b981",
        "CHANGES_REQUESTED": "#f59e0b",
        "BLOCKED": "#ef4444",
    }.get(report.verdict, "#6366f1")

    # Circumference for 40px radius circle = 2 * pi * 40 ≈ 251.2
    circumference = 251.2
    stroke_dashoffset = circumference - (circumference * report.health_score / 100)

    issues_json = json.dumps([
        {
            "file": i.file,
            "line": i.line,
            "severity": i.severity,
            "category": i.category,
            "cwe": i.cwe_id or "General",
            "title": i.title,
            "desc": i.description,
            "fix": i.suggestion or "",
        }
        for i in report.issues
    ])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PR Review Dashboard - {report.title}</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #6366f1;
            --border: #334155;
            --danger: #ef4444;
            --warning: #f59e0b;
            --success: #10b981;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-main);
            line-height: 1.6;
            padding: 30px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 30px;
        }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .brand h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
        .badge-verdict {{
            padding: 8px 18px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 14px;
            letter-spacing: 0.5px;
            background: {verdict_color}22;
            color: {verdict_color};
            border: 1px solid {verdict_color};
        }}
        .hero-grid {{
            display: grid;
            grid-template-columns: 280px 1fr;
            gap: 24px;
            margin-bottom: 30px;
        }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
        }}
        .score-card {{
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .gauge-wrap {{ position: relative; width: 140px; height: 140px; margin-bottom: 12px; }}
        .gauge-svg {{ transform: rotate(-90deg); width: 140px; height: 140px; }}
        .gauge-bg {{ fill: none; stroke: #334155; stroke-width: 10; }}
        .gauge-val {{
            fill: none;
            stroke: {verdict_color};
            stroke-width: 10;
            stroke-linecap: round;
            stroke-dasharray: {circumference};
            stroke-dashoffset: {stroke_dashoffset};
            transition: stroke-dashoffset 1s ease;
        }}
        .gauge-text {{
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            font-size: 32px;
            font-weight: 800;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }}
        .metric-box {{
            background: #0f172a;
            border: 1px solid var(--border);
            padding: 16px;
            border-radius: 8px;
        }}
        .metric-label {{ font-size: 12px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; margin-bottom: 6px; }}
        .metric-value {{ font-size: 20px; font-weight: 700; color: #fff; }}
        .council-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        .council-table th, .council-table td {{
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }}
        .council-table th {{ color: var(--text-muted); font-size: 13px; text-transform: uppercase; }}
        .status-pill {{
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 700;
        }}
        .pill-passed {{ background: #10b98122; color: #10b981; border: 1px solid #10b981; }}
        .pill-warning {{ background: #f59e0b22; color: #f59e0b; border: 1px solid #f59e0b; }}
        .pill-failed {{ background: #ef444422; color: #ef4444; border: 1px solid #ef4444; }}
        .issue-card {{
            background: var(--bg-card);
            border-left: 4px solid #ef4444;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
            border-top: 1px solid var(--border);
            border-right: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
        }}
        .issue-card.HIGH {{ border-left-color: #f59e0b; }}
        .issue-card.MEDIUM {{ border-left-color: #3b82f6; }}
        .issue-card.LOW {{ border-left-color: #64748b; }}
        .issue-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .issue-title {{ font-size: 16px; font-weight: 700; }}
        .issue-badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 4px; }}
        .badge-CRITICAL {{ background: #ef4444; color: #fff; }}
        .badge-HIGH {{ background: #f59e0b; color: #000; }}
        .badge-MEDIUM {{ background: #3b82f6; color: #fff; }}
        .code-box {{
            background: #0f172a;
            border: 1px solid var(--border);
            padding: 12px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 13px;
            margin-top: 10px;
            overflow-x: auto;
            color: #38bdf8;
        }}
        .btn {{
            background: var(--accent);
            color: #fff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }}
        .btn:hover {{ opacity: 0.9; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>🤖 PR Reviewer Council Dashboard</h1>
            </div>
            <div>
                <span class="badge-verdict">{report.verdict}</span>
            </div>
        </header>

        <div class="hero-grid">
            <div class="card score-card">
                <div class="gauge-wrap">
                    <svg class="gauge-svg">
                        <circle class="gauge-bg" cx="70" cy="70" r="40" />
                        <circle class="gauge-val" cx="70" cy="70" r="40" />
                    </svg>
                    <div class="gauge-text">{report.health_score}</div>
                </div>
                <h3>Health Score</h3>
                <p style="color: var(--text-muted); font-size: 13px;">Out of 100 max points</p>
            </div>

            <div class="card">
                <h3 style="margin-bottom: 14px;">Triage Overview</h3>
                <div class="metrics-grid">
                    <div class="metric-box">
                        <div class="metric-label">Classification</div>
                        <div class="metric-value">{report.triage.pr_type}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Volume Sizing</div>
                        <div class="metric-value">{report.triage.size_tier}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Composite Risk</div>
                        <div class="metric-value">{report.triage.risk_level}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Additions / Deletions</div>
                        <div class="metric-value">+{report.triage.total_additions} / -{report.triage.total_deletions}</div>
                    </div>
                </div>
                <p style="margin-top: 14px; color: var(--text-muted); font-size: 14px;"><strong>Target:</strong> {report.title} &bull; <strong>Files:</strong> {report.triage.total_files}</p>
            </div>
        </div>

        <div class="card" style="margin-bottom: 30px;">
            <h3>🏛️ Specialist Agent Council Scorecard</h3>
            <table class="council-table">
                <thead>
                    <tr>
                        <th>Specialist Agent</th>
                        <th>Health Score</th>
                        <th>Status</th>
                        <th>Observation</th>
                    </tr>
                </thead>
                <tbody>
"""

    for s in report.specialist_reviews:
        pill_class = "pill-passed" if s.status == "PASSED" else ("pill-warning" if s.status == "WARNING" else "pill-failed")
        html_content += f"""
                    <tr>
                        <td><strong>{s.agent_name}</strong></td>
                        <td>{s.score}/100</td>
                        <td><span class="status-pill {pill_class}">{s.status}</span></td>
                        <td>{s.summary}</td>
                    </tr>
        """

    html_content += f"""
                </tbody>
            </table>
        </div>

        <h2 style="margin-bottom: 16px;">🔍 Findings & Remediation ({len(report.issues)})</h2>
        <div id="issues-list">
    """

    for issue in report.issues:
        html_content += f"""
            <div class="issue-card {issue.severity}">
                <div class="issue-header">
                    <div class="issue-title">{issue.title}</div>
                    <span class="issue-badge badge-{issue.severity}">{issue.severity}</span>
                </div>
                <div style="color: var(--text-muted); font-size: 13px; margin-bottom: 8px;">
                    <strong>File:</strong> {issue.file}:{issue.line or ''} &bull; <strong>CWE:</strong> {issue.cwe_id or 'N/A'}
                </div>
                <p style="font-size: 14px; margin-bottom: 10px;">{issue.description}</p>
                {"<div class='code-box'><strong>Suggested Fix:</strong><br/>" + issue.suggestion + "</div>" if issue.suggestion else ""}
            </div>
        """

    if report.remediation_patch:
        html_content += f"""
        <div class="card" style="margin-top: 30px;">
            <h3>🩹 Autonomous Remediation Patch</h3>
            <p style="color: var(--text-muted); margin-bottom: 10px; font-size: 14px;">Apply directly to your branch using <code>git apply remediation.patch</code></p>
            <pre class="code-box" style="white-space: pre-wrap; color: #a5f3fc;">{report.remediation_patch}</pre>
        </div>
        """

    html_content += """
    </div>
</body>
</html>
"""
    return html_content

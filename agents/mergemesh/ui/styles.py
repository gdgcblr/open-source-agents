"""Custom CSS styles for MergeMesh's developer-focused dark dashboard."""

from __future__ import annotations

DASHBOARD_CSS = """
<style>
    /* Base container and typography */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
        max-width: 1280px;
    }
    .mm-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1.15rem 1.5rem;
        margin-bottom: 1.2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 1rem;
    }
    .mm-title {
        font-size: 1.65rem;
        font-weight: 700;
        color: #f8fafc;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .mm-subtitle {
        font-size: 0.92rem;
        color: #94a3b8;
        margin-top: 0.2rem;
    }
    .mm-badge-row {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
        align-items: center;
    }
    .mm-badge {
        display: inline-block;
        padding: 0.28rem 0.68rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        font-family: "Consolas", "Monaco", monospace;
        border: 1px solid transparent;
    }
    .mm-badge-fixture {
        background-color: #1e293b;
        color: #cbd5e1;
        border-color: #475569;
    }
    .mm-badge-pass {
        background-color: rgba(34, 197, 94, 0.15);
        color: #4ade80;
        border-color: rgba(34, 197, 94, 0.4);
    }
    .mm-badge-fail {
        background-color: rgba(239, 68, 68, 0.16);
        color: #f87171;
        border-color: rgba(239, 68, 68, 0.45);
    }
    .mm-badge-warn {
        background-color: rgba(245, 158, 11, 0.16);
        color: #fbbf24;
        border-color: rgba(245, 158, 11, 0.45);
    }
    .mm-badge-info {
        background-color: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border-color: rgba(56, 189, 248, 0.4);
    }
    .mm-card {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.9rem;
    }
    .mm-card-fail {
        background-color: rgba(127, 29, 29, 0.22);
        border: 1px solid #ef4444;
        border-left: 5px solid #ef4444;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .mm-card-pass {
        background-color: rgba(20, 83, 45, 0.22);
        border: 1px solid #22c55e;
        border-left: 5px solid #22c55e;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .mm-card-warn {
        background-color: rgba(120, 53, 15, 0.22);
        border: 1px solid #f59e0b;
        border-left: 5px solid #f59e0b;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .mm-ai-box {
        background-color: #111827;
        border: 1px dashed #6366f1;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-top: 0.75rem;
    }
    .mm-metric-label {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        margin-bottom: 0.25rem;
    }
    .mm-metric-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #f8fafc;
        font-family: "Consolas", monospace;
    }
</style>
"""

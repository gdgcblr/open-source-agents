"""Dependency graph builder and Graphviz DOT generator."""

from __future__ import annotations

from domain.models import Finding


def build_dependency_edges(
    provider_repo: str,
    consumer_repo: str,
    interface_type: str = "rest_json",
) -> list[dict[str, str]]:
    """Build directed dependency edges from provider to consumer."""
    return [
        {
            "source": provider_repo,
            "target": consumer_repo,
            "relationship": "provides REST JSON contract to",
            "interface_type": interface_type,
        }
    ]


def build_graphviz_dot(
    provider_repo: str,
    consumer_repo: str,
    findings: list[Finding],
    post_fix_passed: bool = False,
) -> str:
    """Return a clean Graphviz DOT string representing the cross-repository contract status."""
    has_high = any(f.severity in {"CRITICAL", "HIGH"} for f in findings) and not post_fix_passed
    edge_color = "#ef4444" if has_high else "#22c55e"
    consumer_border = "#ef4444" if has_high else "#22c55e"

    if has_high and findings:
        f0 = findings[0]
        if f0.replacement_candidate:
            edge_label = f"BREAKING: '{f0.field}' -> '{f0.replacement_candidate}'\\n(Consumer expects '{f0.field}')"
        else:
            edge_label = f"BREAKING: '{f0.field}' mismatch"
    elif post_fix_passed:
        edge_label = "REMEDIATED: Contract compatible\\n(Post-fix verified PASS)"
    else:
        edge_label = "COMPATIBLE: REST JSON contract verified"

    dot = f"""digraph MergeMeshDependency {{
    rankdir=LR;
    bgcolor="transparent";
    pad="0.25";
    nodesep="0.8";
    ranksep="1.2";
    node [shape=box, style="rounded,filled", fontname="Segoe UI, Helvetica, Arial, sans-serif", fontsize=11, margin="0.22,0.14", penwidth=2];
    edge [fontname="Consolas, monospace", fontsize=10, penwidth=2.2];

    "{provider_repo}" [
        label="{provider_repo}\\n(Provider Service | PR A: PASS)",
        fillcolor="#1e293b",
        color="#38bdf8",
        fontcolor="#f8fafc"
    ];

    "{consumer_repo}" [
        label="{consumer_repo}\\n(Consumer Client | PR B: PASS w/ mock)",
        fillcolor="#1e293b",
        color="{consumer_border}",
        fontcolor="#f8fafc"
    ];

    "{provider_repo}" -> "{consumer_repo}" [
        label="{edge_label}",
        color="{edge_color}",
        fontcolor="{edge_color}"
    ];
}}"""
    return dot

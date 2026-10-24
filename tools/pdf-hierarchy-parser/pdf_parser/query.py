"""Query and export helpers for the hierarchy graph."""

from __future__ import annotations

import networkx as nx


def get_subtree(graph: nx.DiGraph, keyword: str) -> nx.DiGraph | None:
    """Return the subtree rooted at the first heading containing ``keyword``.

    The match is case-insensitive and only considers title/heading nodes.
    Returns ``None`` when no heading matches.
    """
    needle = keyword.strip().lower()
    if not needle:
        return None

    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") not in ("title", "heading"):
            continue
        if needle in attrs.get("text", "").lower():
            descendants = nx.descendants(graph, node_id)
            return graph.subgraph({node_id, *descendants}).copy()

    return None


def get_node_breadcrumbs(graph: nx.DiGraph, node_id: str) -> list[str]:
    """Return the breadcrumb path for ``node_id`` (empty for the root)."""
    return list(graph.nodes[node_id]["breadcrumbs"])


def export_graph_json(graph: nx.DiGraph) -> dict:
    """Export the graph as a JSON-serializable ``{"nodes", "edges"}`` dict."""
    nodes = [{"id": node_id, **attrs} for node_id, attrs in graph.nodes(data=True)]
    edges = [
        {
            "source": source,
            "target": target,
            "relation": attrs.get("relation", ""),
        }
        for source, target, attrs in graph.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}

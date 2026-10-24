"""Build a NetworkX hierarchy graph from normalized Docling items.

Docling reports ``level=1`` for every ``SectionHeaderItem``, so heading depth
must be inferred from section numbering and heading keywords. The resulting
graph is a ``nx.DiGraph`` with a virtual ``root`` node and ``PARENT_OF`` edges.
"""

from __future__ import annotations

import re

import networkx as nx

LEAF_LEVEL = 999

_SECTION_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?(?=\s|$)")

_TITLE_KEYWORDS = {
    "abstract",
    "introduction",
    "background",
    "conclusion",
    "conclusions",
    "references",
    "acknowledgments",
    "acknowledgements",
    "appendix",
    "related work",
    "discussion",
    "methodology",
    "results",
    "summary",
    "bibliography",
    "future work",
}

_LABEL_TO_TYPE = {
    "text": "text",
    "caption": "caption",
    "list_item": "list_item",
    "table": "table",
}


def infer_heading_level(text: str, prev_level: int = 1) -> int:
    """Infer a heading's depth from its text.

    Numbered headings use their dot count (``"3.2.1 Foo"`` -> 3). Known
    top-level keywords such as ``"Abstract"`` map to level 1. Anything else is
    treated as a sub-heading of the current context (``prev_level + 1``).
    """
    text_stripped = text.strip()

    match = _SECTION_NUM_RE.match(text_stripped)
    if match:
        return match.group(1).count(".") + 1

    lower = text_stripped.lower()
    for keyword in _TITLE_KEYWORDS:
        if (
            lower == keyword
            or lower.startswith(keyword + " ")
            or lower.startswith(keyword + ":")
        ):
            return 1

    return prev_level + 1


def build_hierarchy_graph(items: list[dict]) -> nx.DiGraph:
    """Build a directed hierarchy graph from ``convert_pdf`` output.

    Pass 1 assigns every item a node type and inferred level. Pass 2 attaches
    nodes using a heading stack. Pass 3 propagates breadcrumbs from the root.
    """
    graph = nx.DiGraph()
    graph.add_node(
        "root", type="root", level=-1, text="", label="root", breadcrumbs=[]
    )

    nodes: list[tuple[str, dict]] = []
    first_header_seen = False
    prev_heading_level = 0

    for position, item in enumerate(items):
        node_id = f"node_{position}"
        item_class = item.get("class", "")
        label = item.get("label", "")
        text = item.get("text", "") or ""

        if item_class == "SectionHeaderItem":
            if not first_header_seen:
                node_type, level = "title", 0
                first_header_seen = True
            else:
                node_type = "heading"
                level = infer_heading_level(text, prev_heading_level)
            prev_heading_level = level
        else:
            node_type = _LABEL_TO_TYPE.get(label, "text")
            level = LEAF_LEVEL

        nodes.append(
            (
                node_id,
                {
                    "type": node_type,
                    "level": level,
                    "text": text,
                    "label": label,
                    "breadcrumbs": [],
                },
            )
        )

    heading_stack: list[tuple[int, str]] = [(-1, "root")]

    for node_id, attrs in nodes:
        graph.add_node(node_id, **attrs)
        level = attrs["level"]

        if level == LEAF_LEVEL:
            parent_id = heading_stack[-1][1]
        else:
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent_id = heading_stack[-1][1] if heading_stack else "root"
            heading_stack.append((level, node_id))

        graph.add_edge(parent_id, node_id, relation="PARENT_OF")

    for node_id in nx.bfs_tree(graph, "root"):
        if node_id == "root":
            continue
        parent = next(iter(graph.predecessors(node_id)))
        parent_crumbs = graph.nodes[parent]["breadcrumbs"]
        node = graph.nodes[node_id]
        if node["type"] in ("title", "heading"):
            node["breadcrumbs"] = parent_crumbs + [node["text"]]
        else:
            node["breadcrumbs"] = list(parent_crumbs)

    return graph

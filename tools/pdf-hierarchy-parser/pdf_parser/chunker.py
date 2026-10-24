"""Emit breadcrumb-prefixed, size-bounded chunks from a hierarchy graph."""

from __future__ import annotations

import re

import networkx as nx

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def _header_prefix(breadcrumbs: list[str]) -> str:
    return "[" + " > ".join(breadcrumbs) + "]\n"


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split text into pieces of at most ``max_chars`` at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_BOUNDARY_RE.split(text):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        if len(sentence) <= max_chars:
            current = sentence
        else:
            for start in range(0, len(sentence), max_chars):
                pieces.append(sentence[start : start + max_chars])
            current = ""
    if current:
        pieces.append(current)
    return pieces


def hierarchical_chunk(graph: nx.DiGraph, max_chars: int = 1500) -> list[dict]:
    """Walk heading nodes in DFS order and emit context-preserving chunks.

    Each chunk contains the text of a heading's direct content children,
    prefixed with a breadcrumb path. Oversized content is split at sentence
    boundaries, repeating the breadcrumb prefix for every piece.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")

    chunks: list[dict] = []
    chunk_id = 0

    for node_id in nx.dfs_preorder_nodes(graph, "root"):
        node = graph.nodes[node_id]
        if node["type"] not in ("title", "heading"):
            continue

        content_parts = [
            graph.nodes[child]["text"]
            for child in graph.successors(node_id)
            if graph.nodes[child]["type"] not in ("title", "heading")
            and graph.nodes[child]["text"].strip()
        ]
        if not content_parts:
            continue

        content = "\n".join(content_parts)
        breadcrumbs = list(node["breadcrumbs"])
        prefix = _header_prefix(breadcrumbs)

        for piece in _split_text(content, max_chars):
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "breadcrumbs": breadcrumbs,
                    "heading": node["text"],
                    "content": piece,
                    "header_prefix": prefix,
                    "text_with_context": prefix + piece,
                }
            )
            chunk_id += 1

    return chunks

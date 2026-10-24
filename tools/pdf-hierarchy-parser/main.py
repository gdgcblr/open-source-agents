#!/usr/bin/env python3
"""CLI for pdf-hierarchy-parser: tree, chunk, query, and export subcommands."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import networkx as nx
from rich.console import Console
from rich.markup import escape
from rich.tree import Tree

from pdf_parser.chunker import hierarchical_chunk
from pdf_parser.converter import convert_pdf
from pdf_parser.graph import build_hierarchy_graph
from pdf_parser.query import export_graph_json, get_subtree

LOGGER = logging.getLogger("pdf_hierarchy_parser")
console = Console()

_STYLES = {
    "title": "bold cyan",
    "heading": "bold cyan",
    "text": "white",
    "list_item": "white",
    "table": "yellow",
    "caption": "dim",
}


def _load_env() -> None:
    """Load KEY=VALUE pairs from .env if present (no external dependency)."""
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    except OSError:
        pass


def _configure_logging() -> None:
    _load_env()
    level_name = os.getenv("LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    # Quiet verbose Docling loggers unless user asks for debug
    if level > logging.DEBUG:
        for noisy in ("docling", "docling.datamodel", "docling.document_converter",
                      "docling.pipeline", "docling.models"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def _node_label(attrs: dict, max_chars: int = 100) -> str:
    node_type = attrs.get("type", "text")
    style = _STYLES.get(node_type, "white")
    text = attrs.get("text", "")

    if node_type == "table":
        text = "<Table>"
    elif not text:
        text = f"<{node_type}>"

    text = text.replace("\n", " ").strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."

    prefix = "" if node_type in ("title", "heading") else "• "
    return f"[{style}]{escape(prefix + text)}[/]"


def _render_tree(graph: nx.DiGraph, node_id: str, tree: Tree) -> None:
    for child in graph.successors(node_id):
        branch = tree.add(_node_label(graph.nodes[child]))
        _render_tree(graph, child, branch)


def _build_graph(pdf_path: str, do_ocr: bool) -> nx.DiGraph:
    LOGGER.debug("Converting %s (ocr=%s)", pdf_path, do_ocr)
    items = convert_pdf(pdf_path, do_ocr=do_ocr)
    LOGGER.debug("Extracted %d items", len(items))
    return build_hierarchy_graph(items)


def _cmd_tree(args: argparse.Namespace) -> int:
    graph = _build_graph(args.pdf, args.ocr)
    tree = Tree(_node_label(graph.nodes["root"]))
    _render_tree(graph, "root", tree)
    console.print(tree)
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    graph = _build_graph(args.pdf, args.ocr)
    chunks = hierarchical_chunk(graph, max_chars=args.max_chars)
    console.print_json(json.dumps(chunks))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    graph = _build_graph(args.pdf, args.ocr)
    subtree = get_subtree(graph, args.section)
    if subtree is None:
        console.print(f"[red]No heading matched:[/] {escape(args.section)}")
        return 1

    # The root of the subtree is the unique node with in-degree 0 in the subgraph
    roots = [node_id for node_id in subtree.nodes() if subtree.in_degree(node_id) == 0]
    root_id = roots[0] if roots else next(iter(subtree.nodes()))
    tree = Tree(_node_label(subtree.nodes[root_id]))
    _render_tree(subtree, root_id, tree)
    console.print(tree)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    graph = _build_graph(args.pdf, args.ocr)
    payload = json.dumps(export_graph_json(graph), indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        console.print(f"[green]Wrote[/] {escape(args.output)}")
    else:
        console.print_json(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("pdf", help="Path to the input PDF file")
    common.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR (slower; needed for scanned/image-only PDFs)",
    )

    parser = argparse.ArgumentParser(
        prog="pdf-hierarchy-parser",
        description="Parse PDFs into a hierarchy graph and structure-aware chunks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tree_parser = subparsers.add_parser(
        "tree", parents=[common], help="Print the heading hierarchy as a tree"
    )
    tree_parser.set_defaults(func=_cmd_tree)

    chunk_parser = subparsers.add_parser(
        "chunk", parents=[common], help="Emit breadcrumb-prefixed RAG chunks"
    )
    chunk_parser.add_argument(
        "--max-chars",
        type=int,
        default=1500,
        help="Maximum characters per chunk (default: 1500)",
    )
    chunk_parser.set_defaults(func=_cmd_chunk)

    query_parser = subparsers.add_parser(
        "query", parents=[common], help="Show the subtree for a heading keyword"
    )
    query_parser.add_argument(
        "--section", required=True, help="Case-insensitive heading keyword"
    )
    query_parser.set_defaults(func=_cmd_query)

    export_parser = subparsers.add_parser(
        "export", parents=[common], help="Export the graph as JSON"
    )
    export_parser.add_argument(
        "--output", help="Output JSON path (default: stdout)"
    )
    export_parser.set_defaults(func=_cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)

    try:
        return args.func(args)
    except FileNotFoundError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        return 1
    except RuntimeError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())

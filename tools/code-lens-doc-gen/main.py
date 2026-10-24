"""
CodeLens Doc Gen — CLI Entry Point

Usage:
    python main.py scan <path>              Scan a codebase and display its structure
    python main.py generate <path>          Generate full documentation (User + Dev)
    python main.py update <path>            Update docs based on recent git changes

Examples:
    python main.py scan .
    python main.py generate /path/to/project --output ./my-docs
    python main.py update . --base HEAD~3 --head HEAD
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError with spinners/emojis
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Suppress deprecation notice from third-party google.generativeai library
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# Ensure package root is in sys.path when executed directly or from another directory
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from codelens import __version__
from codelens.config import load_config, validate_config
from codelens.scanner import scan_codebase, format_file_tree
from codelens.analyzer import analyze_codebase, condense_for_llm
from codelens.categorizer import categorize_codebase, fallback_categorize
from codelens.generator import generate_documentation, write_documentation
from codelens.diff_analyzer import is_git_repo
from codelens.updater import update_documentation

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="codelens")
def cli():
    """
    CodeLens Doc Gen — Automatic codebase documentation generator.

    Scans your codebase, analyzes its structure, and generates
    categorized documentation (User Docs & Dev Docs) using Google Gemini.
    """
    pass


# =============================================================================
# SCAN Command
# =============================================================================

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="Show detailed file information.")
def scan(path, verbose):
    """Scan a codebase and display its structure.

    This command performs local-only analysis (no LLM calls).
    It walks the file tree, detects languages, and extracts
    structural information using AST parsing and heuristics.
    """
    config = load_config()
    abs_path = str(Path(path).resolve())

    console.print(Panel(
        f"[bold]Scanning:[/bold] {abs_path}",
        title="CodeLens Scanner",
        border_style="blue",
    ))

    # Scan
    codebase_map = scan_codebase(abs_path, config)
    if not codebase_map or not codebase_map.get("files"):
        console.print("[red]No files found to scan.[/red]")
        return

    # Display summary
    _print_scan_summary(codebase_map)

    # Display file tree
    console.print("\n[bold]File Tree:[/bold]")
    tree_str = format_file_tree(codebase_map["file_tree"])
    console.print(tree_str)

    # Analyze if verbose
    if verbose:
        console.print("\n[bold]Detailed Analysis:[/bold]")
        analyses = analyze_codebase(codebase_map)
        _print_detailed_analysis(analyses)


# =============================================================================
# GENERATE Command
# =============================================================================

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output directory for docs (default: from .env or ./docs_output).")
@click.option("--env-file", default=None, help="Path to .env file (default: auto-detect).")
@click.option("--offline", is_flag=True, help="Use rule-based categorization instead of LLM.")
def generate(path, output, env_file, offline):
    """Generate full documentation for a codebase.

    Scans the codebase, categorizes components using Gemini (or
    rule-based fallback with --offline), and generates structured
    User Docs and Dev Docs in Markdown format.
    """
    config = load_config(env_path=env_file)

    if output:
        config.output_dir = output

    abs_path = str(Path(path).resolve())

    console.print(Panel(
        f"[bold]Generating documentation for:[/bold] {abs_path}\n"
        f"[bold]Output directory:[/bold] {config.output_dir}\n"
        f"[bold]LLM Model:[/bold] {config.gemini_model}\n"
        f"[bold]Mode:[/bold] {'Offline (rule-based)' if offline else 'Online (Gemini)'}",
        title="CodeLens Generator",
        border_style="green",
    ))

    # Validate config (API key needed unless offline)
    if not offline:
        errors = validate_config(config)
        if errors:
            for error in errors:
                console.print(f"[red]Config Error:[/red] {error}")
            sys.exit(1)

    # Step 1: Scan
    console.print("\n[bold blue]Step 1/4:[/bold blue] Scanning codebase...")
    codebase_map = scan_codebase(abs_path, config)
    if not codebase_map or not codebase_map.get("files"):
        console.print("[red]No files found to scan.[/red]")
        sys.exit(1)
    _print_scan_summary(codebase_map)

    # Step 2: Analyze
    console.print("\n[bold blue]Step 2/4:[/bold blue] Analyzing code structure...")
    analyses = analyze_codebase(codebase_map)
    total_classes = sum(len(a.get("classes", [])) for a in analyses)
    total_functions = sum(len(a.get("functions", [])) for a in analyses)
    console.print(f"  Found [cyan]{total_classes}[/cyan] classes and [cyan]{total_functions}[/cyan] functions")

    # Step 3: Categorize
    console.print("\n[bold blue]Step 3/4:[/bold blue] Categorizing components...")
    if offline:
        categorization = fallback_categorize(analyses)
        console.print("  Using rule-based categorization (offline mode)")
    else:
        condensed = condense_for_llm(analyses)
        categorization = categorize_codebase(condensed, config)
        if not categorization:
            console.print("  [yellow]LLM categorization failed, falling back to rule-based[/yellow]")
            categorization = fallback_categorize(analyses)

    # Print categorization summary
    user_count = sum(1 for v in categorization.values() if v["category"] == "user")
    dev_count = sum(1 for v in categorization.values() if v["category"] == "dev")
    both_count = sum(1 for v in categorization.values() if v["category"] == "both")
    console.print(f"  📄 User docs: [green]{user_count}[/green] files")
    console.print(f"  🔧 Dev docs:  [blue]{dev_count}[/blue] files")
    console.print(f"  📋 Both:      [yellow]{both_count}[/yellow] files")

    # Step 4: Generate
    console.print("\n[bold blue]Step 4/4:[/bold blue] Generating documentation...")
    if offline:
        # In offline mode, generate basic doc structure without LLM
        docs = _generate_offline_docs(analyses, categorization, codebase_map)
        written_files = write_documentation(docs, config.output_dir)
    else:
        docs = generate_documentation(analyses, categorization, codebase_map, config)
        written_files = write_documentation(docs, config.output_dir)

    # Done
    console.print(Panel(
        f"[bold green]Documentation generated successfully![/bold green]\n\n"
        f"📁 Output: {Path(config.output_dir).resolve()}\n"
        f"📄 Files written: {len(written_files)}\n\n"
        f"[dim]User docs: {config.output_dir}/user-docs/[/dim]\n"
        f"[dim]Dev docs:  {config.output_dir}/dev-docs/[/dim]",
        title="✅ Complete",
        border_style="green",
    ))


# =============================================================================
# UPDATE Command
# =============================================================================

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output directory for docs.")
@click.option("--base", default="HEAD~1", help="Base git ref (default: HEAD~1).")
@click.option("--head", default="HEAD", help="Head git ref (default: HEAD).")
@click.option("--env-file", default=None, help="Path to .env file.")
def update(path, output, base, head, env_file):
    """Update documentation based on recent git changes.

    Detects which files changed between two git refs,
    re-analyzes only those files, and updates the affected
    documentation sections. Much faster than full regeneration.

    Requires the project to be a git repository.
    """
    config = load_config(env_path=env_file)
    if output:
        config.output_dir = output

    abs_path = str(Path(path).resolve())

    # Validate
    errors = validate_config(config)
    if errors:
        for error in errors:
            console.print(f"[red]Config Error:[/red] {error}")
        sys.exit(1)

    if not is_git_repo(abs_path):
        console.print(f"[red]Error:[/red] '{abs_path}' is not a git repository.")
        console.print("[dim]The 'update' command requires git to detect changes.[/dim]")
        console.print("[dim]Use 'generate' instead for non-git projects.[/dim]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Updating docs for:[/bold] {abs_path}\n"
        f"[bold]Diff range:[/bold] {base}..{head}\n"
        f"[bold]Output:[/bold] {config.output_dir}",
        title="CodeLens Updater",
        border_style="yellow",
    ))

    result = update_documentation(abs_path, config, base_ref=base, head_ref=head)

    if result["status"] == "no_changes":
        console.print("[green]✅ No changes detected. Documentation is up to date.[/green]")
    elif result["status"] == "error":
        console.print("[red]❌ Update failed. See errors above.[/red]")
        sys.exit(1)
    else:
        console.print(Panel(
            f"[bold green]Documentation updated![/bold green]\n"
            f"Changed files: {len(result.get('changed_files', []))}\n"
            f"Docs updated: {len(result.get('updated_docs', []))}",
            title="✅ Update Complete",
            border_style="green",
        ))


# =============================================================================
# SERVE Command (Documentation UI)
# =============================================================================

@cli.command()
@click.option("--dir", "-d", default=None, help="Directory containing generated docs (default: ./docs_output).")
@click.option("--port", "-p", default=8000, help="Port to serve on (default: 8000).")
@click.option("--open-browser/--no-open", default=True, help="Automatically open browser.")
def serve(dir, port, open_browser):
    """Launch an interactive web UI to view the generated documentation."""
    import http.server
    import socketserver
    import webbrowser
    import os

    config = load_config()
    target_dir = Path(dir or config.output_dir).resolve()

    if not target_dir.exists() or not (target_dir / "index.html").exists():
        console.print(f"[red]Error:[/red] Documentation not found in '{target_dir}'.")
        console.print("[dim]Run 'python main.py generate .' first to generate documentation.[/dim]")
        sys.exit(1)

    console.print(Panel(
        f"[bold green]Starting Documentation Web Server[/bold green]\n\n"
        f"🌐 URL: [cyan]http://localhost:{port}[/cyan]\n"
        f"📁 Serving: [dim]{target_dir}[/dim]\n\n"
        f"Press [bold]Ctrl+C[/bold] to stop the server.",
        title="📖 CodeLens Docs UI",
        border_style="green",
    ))

    os.chdir(target_dir)

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Keep terminal clean

    if open_browser:
        webbrowser.open(f"http://localhost:{port}")

    with socketserver.TCPServer(("", port), CustomHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Documentation server stopped.[/yellow]")


# =============================================================================
# Helper Functions
# =============================================================================

def _print_scan_summary(codebase_map: dict):
    """Print a formatted summary table of the scan results."""
    table = Table(title="Scan Summary", border_style="blue")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Total files", str(codebase_map["total_files"]))
    table.add_row("Total lines", f"{codebase_map['total_lines']:,}")
    table.add_row("Skipped files", str(codebase_map.get("skipped_files", 0)))

    console.print(table)

    # Language breakdown
    if codebase_map.get("languages"):
        lang_table = Table(title="Languages Detected", border_style="dim")
        lang_table.add_column("Language", style="bold")
        lang_table.add_column("Files", style="cyan", justify="right")

        sorted_langs = sorted(
            codebase_map["languages"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for lang, count in sorted_langs:
            lang_table.add_row(lang, str(count))

        console.print(lang_table)


def _print_detailed_analysis(analyses: list[dict]):
    """Print detailed analysis information for each file."""
    for analysis in analyses:
        if not (analysis.get("classes") or analysis.get("functions") or analysis.get("config_keys")):
            continue

        console.print(f"\n[bold]{analysis['path']}[/bold] ({analysis['language']})")

        if analysis.get("module_docstring"):
            console.print(f"  [dim]{analysis['module_docstring'][:100]}[/dim]")

        for cls in analysis.get("classes", []):
            vis = "🔒" if cls.get("is_private") else "🌐"
            console.print(f"  {vis} class [cyan]{cls['name']}[/cyan]")
            for method in cls.get("methods", []):
                m_vis = "🔒" if method.get("is_private") else "🌐"
                console.print(f"    {m_vis} {method['name']}()")

        for func in analysis.get("functions", []):
            vis = "🔒" if func.get("is_private") else "🌐"
            console.print(f"  {vis} def [green]{func['name']}()[/green]")

        for key in analysis.get("config_keys", []):
            console.print(f"  🔑 {key}")


def _generate_offline_docs(analyses, categorization, codebase_map):
    """
    Generate basic documentation without LLM calls (offline mode).
    Produces structured markdown from the analysis data directly.
    """
    user_content_lines = ["# User Documentation\n"]
    user_content_lines.append(f"*Auto-generated by CodeLens Doc Gen v{__version__}*\n")
    user_content_lines.append("---\n")

    dev_content_lines = ["# Developer Documentation\n"]
    dev_content_lines.append(f"*Auto-generated by CodeLens Doc Gen v{__version__}*\n")
    dev_content_lines.append("---\n")

    for analysis in analyses:
        path = analysis["path"]
        cat_info = categorization.get(path, {"category": "both"})
        category = cat_info.get("category", "both")

        section = _build_offline_section(analysis)

        if category in ("user", "both"):
            user_content_lines.extend(section)
        if category in ("dev", "both"):
            dev_content_lines.extend(section)

    return {
        "user_docs": {"user-guide.md": "\n".join(user_content_lines)},
        "dev_docs": {"developer-guide.md": "\n".join(dev_content_lines)},
        "metadata": {
            "total_files_analyzed": len(analyses),
            "root_path": codebase_map.get("root_path", ""),
            "mode": "offline",
        },
    }


def _build_offline_section(analysis: dict) -> list[str]:
    """Build a markdown section for a single file in offline mode."""
    lines = []
    lines.append(f"\n## `{analysis['path']}`\n")
    lines.append(f"**Language:** {analysis['language']}\n")

    if analysis.get("module_docstring"):
        lines.append(f"> {analysis['module_docstring']}\n")

    if analysis.get("classes"):
        lines.append("### Classes\n")
        for cls in analysis["classes"]:
            vis = "Private" if cls.get("is_private") else "Public"
            lines.append(f"#### `{cls['name']}` ({vis})\n")
            if cls.get("docstring"):
                lines.append(f"{cls['docstring']}\n")
            if cls.get("methods"):
                lines.append("| Method | Visibility | Async |")
                lines.append("|:---|:---|:---|")
                for m in cls["methods"]:
                    m_vis = "Private" if m.get("is_private") else "Public"
                    m_async = "Yes" if m.get("is_async") else "No"
                    lines.append(f"| `{m['name']}()` | {m_vis} | {m_async} |")
                lines.append("")

    if analysis.get("functions"):
        lines.append("### Functions\n")
        lines.append("| Function | Visibility | Async |")
        lines.append("|:---|:---|:---|")
        for func in analysis["functions"]:
            vis = "Private" if func.get("is_private") else "Public"
            is_async = "Yes" if func.get("is_async") else "No"
            lines.append(f"| `{func['name']}()` | {vis} | {is_async} |")
        lines.append("")

    if analysis.get("config_keys"):
        lines.append("### Configuration Keys\n")
        for key in analysis["config_keys"]:
            lines.append(f"- `{key}`")
        lines.append("")

    return lines


if __name__ == "__main__":
    cli()

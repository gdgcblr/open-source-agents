
import argparse
import sys
from pathlib import Path

from code_reader import read_source_file, split_code, discover_source_files
from summarizer import summarize_code , analyze_project


def analyze_file(file_path: Path, output_dir: Path) -> str:
    """Summarize one source file and save its report."""
    source = read_source_file(str(file_path))
    chunks = split_code(source, max_lines=100)

    print(f"\nAnalyzing: {file_path}")
    print(f"Lines: {len(source.splitlines())} | Chunks: {len(chunks)}")

    summary = summarize_code(chunks)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{file_path.stem}-summary.md"

    report = (
        f"# CodeLens AI Summary: {file_path.name}\n\n"
        "> AI-generated explanation. Verify important details against the source.\n\n"
        f"{summary}\n"
    )
    output_file.write_text(report, encoding="utf-8")

    print(f"Saved: {output_file}")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Explain source files or analyze a project using CodeLens AI."
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", help="Path to one source file.")
    mode.add_argument("--directory", help="Path to a project directory.")

    parser.add_argument(
        "--output",
        default="output",
        help="Directory for generated Markdown reports (default: output).",
    )

    args = parser.parse_args()

    try:
        output_dir = Path(args.output)

        if args.file:
            file_path = Path(args.file).expanduser().resolve()
            analyze_file(file_path, output_dir)
            return

        project_dir = Path(args.directory).expanduser().resolve()
        source_files = discover_source_files(str(project_dir))

        if not source_files:
            raise ValueError("No supported source files found in this directory.")

        print(f"Project: {project_dir}")
        print(f"Source files found: {len(source_files)}")

        file_summaries = []

        for file_path in source_files:
            relative_path = file_path.relative_to(project_dir)
            summary = analyze_file(file_path, output_dir / "files")
            file_summaries.append(
                f"## File: {relative_path}\n\n{summary}"
            )

        
        print("\nGenerating project architecture and insights...")
        architecture = analyze_project(file_summaries)

        project_prompt = "\n\n".join(file_summaries)

        project_report = (
            "# CodeLens AI — Project Overview\n\n"
            f"**Project directory:** `{project_dir}`\n\n"
            f"**Files analyzed:** {len(source_files)}\n\n"
            "> AI-generated analysis. Verify important details against the source.\n\n"
            "## Project Architecture and Insights\n\n"
            f"{architecture}\n\n"
            "---\n\n"
            "## File-by-file Analysis\n\n"
            f"{project_prompt}\n"
        )


        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "project-summary.md"
        report_path.write_text(project_report, encoding="utf-8")

        print(f"\nProject report saved to: {report_path.resolve()}")

    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error ({type(exc).__name__}): {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

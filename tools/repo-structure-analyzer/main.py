import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

IGNORE_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env",
    "node_modules", "dist", "build", ".next", ".turbo",
    ".idea", ".vscode", ".DS_Store"
}

IMPORTANT_FILES = {
    "readme.md",
    "readme",
    "requirements.txt",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "dockerfile",
    "docker-compose.yml",
    "makefile",
    ".gitignore"
}

def iter_repo_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            if path.name in IGNORE_DIRS:
                continue
            continue

        if path.is_file():
            yield path

def summarize_repo(root: Path):
    top_dirs = defaultdict(int)
    extension_counts = Counter()
    important_files = []
    total_files = 0

    for path in iter_repo_files(root):
        rel_path = path.relative_to(root)

        if rel_path.parent != Path("."):
            parent_name = rel_path.parts[0]
            if parent_name not in IGNORE_DIRS:
                top_dirs[parent_name] += 1

        ext = path.suffix.lower() or "(no extension)"
        extension_counts[ext] += 1
        total_files += 1

        if path.name.lower() in IMPORTANT_FILES:
            important_files.append(str(rel_path))

    top_dirs_sorted = [
        {"name": name, "count": count}
        for name, count in sorted(top_dirs.items(), key=lambda x: (-x[1], x[0]))[:10]
    ]

    ext_sorted = [
        {"extension": ext, "count": count}
        for ext, count in extension_counts.most_common(10)
    ]

    return {
        "root": str(root),
        "total_files": total_files,
        "top_directories": top_dirs_sorted,
        "extensions": ext_sorted,
        "important_files": sorted(important_files)
    }

def print_summary(summary):
    print("Repository Summary")
    print("------------------")
    print(f"Root: {summary['root']}")
    print(f"Total files: {summary['total_files']}")
    print()

    print("Top directories:")
    if summary["top_directories"]:
        for item in summary["top_directories"]:
            print(f" - {item['name']}: {item['count']} files")
    else:
        print(" - No project directories detected")

    print()
    print("Important files:")
    if summary["important_files"]:
        for item in summary["important_files"]:
            print(f" - {item}")
    else:
        print(" - No major project files detected")

    print()
    print("File extensions:")
    if summary["extensions"]:
        for item in summary["extensions"]:
            print(f" - {item['extension']}: {item['count']}")
    else:
        print(" - No files found")

def main():
    parser = argparse.ArgumentParser(description="Summarize a repository structure")
    parser.add_argument("path", nargs="?", default=".", help="Repository path to scan")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    args = parser.parse_args()

    root = Path(args.path).resolve()

    if not root.exists():
        print(f"Path does not exist: {root}")
        return 1

    if not root.is_dir():
        print(f"Not a directory: {root}")
        return 1

    summary = summarize_repo(root)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_summary(summary)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
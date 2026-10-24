
#!/usr/bin/env python3
"""Check whether a project folder has basic setup files."""

import argparse
from pathlib import Path

CHECKS = [
    {
        "name": "README.md",
        "description": "Project documentation",
        "paths": ["README.md", "readme.md", "README"],
    },
    {
        "name": "Dependency manifest",
        "description": "A file declaring project dependencies",
        "paths": [
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
        ],
    },
    {
        "name": ".gitignore",
        "description": "Rules for files Git should ignore",
        "paths": [".gitignore"],
    },
    {
        "name": ".env.example",
        "description": "Example environment configuration",
        "paths": [".env.example", ".env.example.template"],
    },
]


def check_project(project_path: Path) -> int:
    """Print a readiness report and return the number of passed checks."""
    if not project_path.exists() or not project_path.is_dir():
        print(f"Error: '{project_path}' is not a valid directory.")
        return -1

    print(f"\nProject Readiness Report: {project_path.resolve()}\n")
    passed = 0

    for check in CHECKS:
        found = any((project_path / name).is_file()
                    for name in check["paths"])

        if found:
            print(f"[OK]      {check['name']} — {check['description']}")
            passed += 1
        else:
            print(f"[MISSING] {check['name']} — {check['description']}")

    total = len(CHECKS)
    print(f"\nResult: {passed}/{total} checks passed.")

    if passed == total:
        print("Great! All basic file checks passed.")
    else:
        print("Suggestions:")
        for check in CHECKS:
            if not any((project_path / name).is_file()
                       for name in check["paths"]):
                print(f"- Add {check['name']}: {check['description']}.")

    print("\nNote: This is a basic file-presence check, not a full security audit.")
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check basic setup files in a software project."
    )
    parser.add_argument(
        "project_directory",
        nargs="?",
        default=".",
        help="Path to the project directory (defaults to current directory).",
    )
    args = parser.parse_args()

    result = check_project(Path(args.project_directory).expanduser())
    if result == -1:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

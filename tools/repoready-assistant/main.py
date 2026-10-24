
"""RepoReady: a read-only repository setup readiness checker."""

import argparse
from pathlib import Path

MANIFESTS = [
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
]


def inspect_repository(root: Path) -> dict:
    root = root.expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Expected a directory: {root}")

    results = []

    def add(status, check, message):
        results.append({
            "status": status,
            "check": check,
            "message": message,
        })

    for filename, label in [
        ("README.md", "Documentation"),
        (".gitignore", "Git ignore rules"),
        ("LICENSE", "License"),
    ]:
        if (root / filename).is_file():
            add("PASS", label, f"{filename} exists")
        else:
            add("WARN", label, f"{filename} is missing")

    manifest = next(
        (name for name in MANIFESTS if (root / name).is_file()),
        None,
    )
    if manifest:
        add("PASS", "Dependencies", f"{manifest} exists")
    else:
        add("WARN", "Dependencies", "No supported dependency manifest found")

    has_tests = (
        (root / "tests").is_dir()
        or (root / "test").is_dir()
        or any(root.glob("test_*.py"))
        or any(root.glob("*_test.py"))
    )
    add(
        "PASS" if has_tests else "WARN",
        "Tests",
        "Test files found" if has_tests else "No common test files found",
    )

    workflows = root / ".github" / "workflows"
    has_ci = workflows.is_dir() and any(workflows.iterdir())
    add(
        "PASS" if has_ci else "WARN",
        "Continuous integration",
        "GitHub Actions workflows found"
        if has_ci else "No GitHub Actions workflow found",
    )

    has_env = (root / ".env.example").is_file()
    add(
        "PASS" if has_env else "INFO",
        "Environment template",
        ".env.example exists"
        if has_env else "Optional .env.example not found",
    )

    return {
        "repository": str(root),
        "results": results,
        "passed": sum(item["status"] == "PASS" for item in results),
        "warnings": sum(item["status"] == "WARN" for item in results),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check repository setup readiness without modifying files."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository path (defaults to current directory)",
    )
    args = parser.parse_args()

    try:
        report = inspect_repository(Path(args.path))
    except (FileNotFoundError, NotADirectoryError) as exc:
        parser.error(str(exc))

    print(f"\nRepoReady Report\nRepository: {report['repository']}")
    print("-" * 60)

    for item in report["results"]:
        print(
            f"[{item['status']}] {item['check']}: {item['message']}"
        )

    print("-" * 60)
    print(f"Passed: {report['passed']} | Warnings: {report['warnings']}")
    print("Advisory checks only — this is not a security audit.")


if __name__ == "__main__":
    main()

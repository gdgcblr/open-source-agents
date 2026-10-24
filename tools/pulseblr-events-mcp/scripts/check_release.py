"""Check contribution scope, forbidden files, common secret patterns and built archives.

This is a local release guard, not a complete secret scanner or security audit.
It prints only paths and rule names, never matched values.
"""

import argparse
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "google-api-key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "github-token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "aws-access-key": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "anthropic-api-key": re.compile(rb"sk-ant-api[0-9A-Za-z_-]{30,}"),
    "openai-project-key": re.compile(rb"sk-proj-[A-Za-z0-9_-]{30,}"),
    "mongodb-credentials": re.compile(rb"mongodb(?:\+srv)?://[^\s/\"']+:[^\s/\"']+@"),
}


def forbidden(name):
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return True
    if any(
        part in {".venv", "venv", "__pycache__", ".pytest_cache", ".git"} for part in path.parts
    ):
        return True
    if path.name in {".env", "credentials.json", "service-account.json"}:
        return True
    if path.name.startswith(".env.") and path.name != ".env.example":
        return True
    return path.suffix.lower() in {".pem", ".key", ".pyc", ".p12", ".pfx"}


def inspect_bytes(name, data, problems):
    if forbidden(name):
        problems.append((name, "forbidden-file"))
        return
    for rule, pattern in SECRET_PATTERNS.items():
        if pattern.search(data):
            problems.append((name, rule))


def git_lines(*arguments):
    result = subprocess.run(
        ["git", "-C", str(PROJECT), *arguments],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8").splitlines()


def check(scan_archives=False):
    root = Path(git_lines("rev-parse", "--show-toplevel")[0])
    prefix = PROJECT.relative_to(root).as_posix() + "/"
    changed = set(git_lines("diff", "--name-only", "HEAD"))
    changed.update(
        git_lines("ls-files", "--others", "--exclude-standard", "--full-name", "--", ":/")
    )
    problems = [
        (name, "outside-contribution-scope")
        for name in sorted(changed)
        if not name.startswith(prefix) and name != "tools/README.md"
    ]
    candidates = git_lines(
        "ls-files", "--cached", "--others", "--exclude-standard", "--full-name", "--", "."
    )
    for name in candidates:
        if not name.startswith(prefix):
            continue
        file = root / name
        if file.is_file():
            if forbidden(name):
                problems.append((name, "forbidden-file"))
            else:
                inspect_bytes(name, file.read_bytes(), problems)
    archive_count = 0
    wheel_count = 0
    sdist_count = 0
    if scan_archives:
        for archive in sorted((PROJECT / "dist").glob("*")):
            if archive.suffix == ".whl":
                with zipfile.ZipFile(archive) as wheel:
                    for name in wheel.namelist():
                        inspect_bytes(name, wheel.read(name), problems)
                archive_count += 1
                wheel_count += 1
            elif archive.name.endswith(".tar.gz"):
                with tarfile.open(archive) as sdist:
                    for member in sdist.getmembers():
                        if member.issym() or member.islnk():
                            problems.append((member.name, "archive-link"))
                        elif member.isfile():
                            inspect_bytes(member.name, sdist.extractfile(member).read(), problems)
                archive_count += 1
                sdist_count += 1
        if (wheel_count, sdist_count) != (1, 1):
            problems.append(("dist/", "expected-one-wheel-and-one-sdist"))
    return candidates, archive_count, sorted(set(problems))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archives", action="store_true", help="also inspect built wheel and sdist"
    )
    args = parser.parse_args()
    try:
        candidates, archives, problems = check(args.archives)
    except (OSError, subprocess.CalledProcessError, ValueError):
        print(
            "Release check could not inspect this Git checkout and its archives.", file=sys.stderr
        )
        raise SystemExit(1) from None
    if problems:
        for name, rule in problems:
            print(f"FAIL {rule}: {name}")
        raise SystemExit(1)
    print(
        f"Release guard passed: {len(candidates)} candidate files, {archives} archives; no rule matches."
    )
    print("Pattern checks are limited; review the staged diff before sharing.")


if __name__ == "__main__":
    main()

import pathlib
import re
import subprocess
import sys


PROJECT = pathlib.Path("agents/contribution-mentor")
README = PROJECT / "README.md"
ENV_EXAMPLE = PROJECT / ".env.example"
SECRET_PATTERNS = (
    re.compile(r"AQ\.[A-Za-z0-9_-]{30,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?m)^[ \t]*(?:LLM_API_KEY|GITHUB_TOKEN)[ \t]*=[ \t]*[^ \t\r\n#]+"),
)


def main():
    root = pathlib.Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
    )
    readme = (root / README).read_text(encoding="utf-8")
    required_sections = (
        "## Overview",
        "## Technical Stack",
        "## Architecture & Data Flow",
        "## Prerequisites",
        "## Installation & Setup",
        "## Configuration",
        "## How to Run",
        "## Example Input & Output",
        "## How to Test",
        "## Known Limitations",
        "## Security & Privacy Considerations",
        "## Future Improvements",
        "## License",
    )
    missing = [heading for heading in required_sections if heading not in readme]
    if missing:
        raise ValueError("README is missing required sections: " + ", ".join(missing))

    template = (root / ENV_EXAMPLE).read_text(encoding="utf-8")
    for key in ("LLM_API_KEY", "GITHUB_TOKEN"):
        match = re.search(rf"(?m)^{key}=(.*)$", template)
        if not match:
            raise ValueError(f".env.example is missing {key}")
        if match.group(1).strip():
            raise ValueError(f".env.example must not contain a value for {key}")

    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode("utf-8").split("\0")
    if str(PROJECT / ".env") in tracked:
        raise ValueError("local .env must not be tracked")
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", str(PROJECT / ".env")], cwd=root
    )
    if ignored.returncode != 0:
        raise ValueError("local .env is not ignored by Git")
    allowed_paths = {
        "agents/README.md",
        ".github/workflows/contribution-mentor-ci.yml",
    }
    for relative in filter(
        lambda path: path
        and (
            path.startswith(str(PROJECT) + "/")
            or path in allowed_paths
        ),
        tracked,
    ):
        path = root / relative
        if path.name == ".env" or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                raise ValueError(f"potential credential found in {relative}")

    print("Documentation, environment template, and tracked-secret checks passed.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"CI validation failed: {error}", file=sys.stderr)
        sys.exit(1)

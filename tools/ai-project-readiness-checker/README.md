
# AI Project Readiness Checker

A beginner-friendly command-line tool that checks whether a software
project contains essential setup and documentation files.

## Features

- Checks for a README file.
- Looks for a dependency manifest.
- Checks for a `.gitignore` file.
- Checks for an `.env.example` file.
- Prints a report with actionable suggestions.
- Uses Python's standard library and requires no third-party packages.

## Requirements

- Python 3.10 or later.
- A terminal.

No API key or internet connection is required to run the checker.

## Installation

Clone or download this repository, then open a terminal.

Move into the tool's directory:

```bash
cd tools/ai-project-readiness-checker
```

No additional package installation is required.

## Usage

Check the current directory:

```bash
python3 checker.py
```

Check another project directory:

```bash
python3 checker.py /path/to/your/project
```

Replace `/path/to/your/project` with the actual directory you want
to inspect.

## Example Output

```text
Project Readiness Report: /path/to/example

[OK]      README.md — Project documentation
[MISSING] Dependency manifest — A file declaring project dependencies
[OK]      .gitignore — Rules for files Git should ignore
[OK]      .env.example — Example environment configuration

Result: 3/4 checks passed.
```

The output above is illustrative. Results depend on the files in
the directory being checked.

## Testing

Run the checker against its own directory:

```bash
python3 checker.py .
```

The checker reports which expected files are present and which are
missing.

## How It Works

The tool uses Python's `pathlib` module to inspect the selected
directory and checks for a small set of conventional filenames.
It then prints the results and suggests missing files.

## Limitations

- Checks file presence, not file contents or quality.
- Does not perform a security audit.
- Does not install dependencies or create missing files.
- Does not currently use an AI model; the current implementation
  is a lightweight, rule-based checker.

## Future Improvements

- Add optional AI-powered explanations.
- Add automated unit tests.
- Detect additional project types and manifest formats.
- Provide machine-readable JSON reports.

## License

Refer to the license terms of the parent repository.

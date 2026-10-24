# First PR Compass

> Generate a read-only, evidence-backed onboarding report for a local repository or public GitHub project so new contributors can learn how to set it up, test it, and find a possible first task.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: People exploring an unfamiliar codebase often have to hunt across documentation, configuration, and source files to learn how to get started and what to contribute.
- **Intended Users**: Open-source newcomers, maintainers improving onboarding, and mentors helping contributors find a first task.

### Key Features
- Finds documented setup commands, recognized test commands, and contribution guidance.
- Suggests up to five candidates based only on explicit comment-form `TODO`, `FIXME`, or `XXX` markers in supported source files.
- Gives each finding a repository-relative file and line reference; writes Markdown or JSON.
- Filters common templates, fixtures, generated folders, and example/test directories to reduce misleading results.
- Accepts a local folder or public `github.com/owner/repository` URL.
- Generates GitHub file-and-line links for remote repository findings.
- Never executes commands or modifies the analyzed repository.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Standard-library Python CLI; no LLM or agent framework is required.
- **Models**: None.
- **External APIs / Tools**: Public GitHub REST API for repository metadata and archive downloads.

---

## Architecture & Data Flow

```text
[Local path] ----------------------+
                                    v
[Public GitHub URL] --> [Bounded temporary download] --> [Read-only scanner]
                                                            |
                                               [Findings with evidence]
                                                  /             \
                                                 v               v
                                        [Markdown report]   [JSON report]
```

GitHub support uses the public GitHub API to find a repository's default branch and download its ZIP archive. The archive is extracted into a temporary directory, analyzed with the same local scanner, and deleted afterward. Downloads are capped at 50 MB, extracted files at 150 MB total, and extraction rejects unsafe paths and links.

The scanner skips common generated/dependency directories, templates, fixtures, environment files, likely credential files, symlinks, binary files, and files larger than 1 MB. Setup and test commands are detected from a limited set of common commands in relevant documentation/configuration. Starter-task scanning looks for comment-form markers in supported source-file extensions and excludes test, fixture, and example directories.

---

## Prerequisites

- Python 3.10 or newer
- `pip`
- A local repository directory or a public GitHub repository URL
- Network access only when analyzing a GitHub URL

No API key is needed for public GitHub repositories. GitHub applies unauthenticated API rate limits; private repositories are not supported.

---

## Installation & Setup

From the repository root:

```powershell
cd tools/first-pr-compass
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

If PowerShell blocks virtual-environment activation, install using `.venv\Scripts\python.exe -m pip install -e .`, then run `.venv\Scripts\first-pr-compass.exe`.

---

## Configuration & Environment Variables

No environment variables are required. `.env.example` is included to match the repository contribution template; it contains no secrets and does not need to be copied.

---

## How to Run

Analyze a local repository and write a Markdown report:

```powershell
first-pr-compass "C:\path\to\repository" --output -
```

Analyze a public GitHub repository (default branch) and print the report:

```powershell
guide-me-to-contribute "https://github.com/owner/repository"
```

The friendly aliases are shortcuts to the same CLI workflow:

```powershell
get-report "https://github.com/owner/repository"
guide-me-to-contribute "C:\path\to\local-repository"
```

`get-report` writes `first-pr-compass-report.md` by default. `guide-me-to-contribute` prints Markdown to the terminal by default. Both accept `--output` and `--format`.

Analyze a specific branch, tag, or commit:

```powershell
get-report "https://github.com/owner/repository" --ref "feature/docs"
```

Write JSON to a file:

```powershell
first-pr-compass "https://github.com/owner/repository" --format json --output "reports\onboarding.json"
```

Use the `.venv\Scripts\` executable prefix if the environment is not activated. The report shows source paths and line numbers; GitHub findings link directly to the analyzed ref. Test/setup commands come from repository content and must be reviewed before running.

---

## Example Input & Output

### Example Input

```powershell
guide-me-to-contribute "https://github.com/owner/repository"
```

### Example Output

```markdown
# First PR Compass report

## Setup steps
- Setup command - Install/build command found in project documentation.
  - Evidence: [README.md:5](https://github.com/owner/repository/blob/main/README.md#L5)

## Tests
- Test command - Test command found in project documentation or configuration.
  - Evidence: [README.md:9](https://github.com/owner/repository/blob/main/README.md#L9)
  - Command: `python -m unittest discover -s tests -v`

## Starter task candidates
- validate the record format before parsing — Potential starter task from an explicit TODO/FIXME/XXX marker.
  - Evidence: [src/example.py:2](https://github.com/owner/repository/blob/main/src/example.py#L2)
```

Output depends on the analyzed repository. If evidence is not found, the report says so instead of inventing setup commands or tasks.

---

## How to Test

From this directory, run the automated tests:

```powershell
python -m unittest discover -s tests -v
```

Test the actual CLI end to end against the included offline fixture:

```powershell
guide-me-to-contribute "tests\fixtures\sample-repo"
```

The fixture includes setup/test instructions, contribution guidance, and a source TODO so that all report sections can be checked without API keys or network access.

To check whether the report is useful for this repository, run from this directory:

```powershell
.\.venv\Scripts\first-pr-compass.exe "..\.." --output "$env:TEMP\first-pr-compass-report.md"
Get-Content "$env:TEMP\first-pr-compass-report.md"
```

Review every evidence link against the named file and line. Setup and test commands should be real commands documented by the analyzed project, not generic template examples. If a section says no evidence was found, verify manually before concluding the repository has no setup, tests, or contribution process.

To test GitHub fetching, use a public repository and save the output outside the project:

```powershell
get-report "https://github.com/psf/requests" --output "$env:TEMP\requests-onboarding.md"
Get-Content "$env:TEMP\requests-onboarding.md"
```

For a specific ref, add `--ref "main"` or another existing branch/tag. Inspect the report's repository/ref header and click an evidence link to confirm it points at the matching GitHub file and line. GitHub API/network failure should produce an explicit error and a non-zero exit code.

---

## Known Limitations

- The tool can inspect documentation for any language. Source TODO scanning supports common languages including Python, JavaScript/TypeScript, Java, C/C++, C#, Go, Rust, Ruby, PHP, Kotlin, Swift, Dart, Elixir, Erlang, Haskell, Lua, R, Scala, SQL, Terraform, PowerShell, Fortran, and Vue/Svelte components. This is not a promise to parse every language: uncommon extensions/comment syntax and ecosystem-specific setup/test commands may not be recognized.
- Only public GitHub repositories are supported. GitHub unauthenticated API rate limits apply; private repositories and GitHub Enterprise are not supported.
- Setup commands are detected from documentation, while tests are recognized from documentation and common project/CI configuration files. Unusual project-specific commands may not be detected; commands may need adjustment for a nested package or a specific working directory.
- Starter-task candidates rely on explicit `TODO`, `FIXME`, or `XXX` markers. The tool does not prove that a marker is still relevant or suitable for a newcomer.
- File and directory exclusions are conservative heuristics; scan notes report files that could not be read or were skipped due to size/encoding.
- Reports use repository-relative links with line anchors. The exact way those links open depends on the Markdown viewer.

---

## Security & Privacy Considerations

- **Secrets Handling**: The tool does not load credentials and skips common environment and credential filenames.
- **Data Privacy**: For local paths, analysis stays on the local machine. For GitHub URLs, the tool contacts GitHub's public API and downloads the public source archive to a temporary local directory; it does not upload repository content to another service.
- **Safety**: The scanner is read-only and never executes commands found in project files. Review suggested commands before running them.

---

## Future Improvements

- [ ] Improve ecosystem-specific setup and test command detection.
- [ ] Add configurable task ranking while preserving evidence and uncertainty labels.

---

## License

This project is contributed under the repository's MIT license.

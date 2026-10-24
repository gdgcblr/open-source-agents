# Release Notes Drafter

> Drafts release notes from merged pull requests so maintainers stop writing them by hand.

## Overview
Maintainers of small open-source projects spend an hour per release summarising merged PRs.
This CLI reads the merged PRs between two tags with the GitHub API and asks Gemini to group them into
Features, Fixes and Breaking Changes. It is for maintainers who tag releases on GitHub.

## Technical Stack
- Python 3.12, Typer, google-genai SDK (Gemini 3.6 Flash), GitHub REST API.

## Architecture & Data Flow
`git tag` range -> GitHub API (list merged PRs) -> prompt with PR titles and labels -> Gemini ->
Markdown printed to stdout. Nothing is written to the repository.

## Prerequisites
- Python 3.11+
- A GitHub token with read access to the repository (public repos work without one, but are limited to
  60 requests per hour)
- A Gemini API key from Google AI Studio

## Installation & Setup
```bash
cd tools/release-notes-drafter
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # then add GEMINI_API_KEY and GITHUB_TOKEN
```

## Configuration & Environment Variables
| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | none | Gemini key |
| `GITHUB_TOKEN` | No | none | Raises the GitHub rate limit |
| `MODEL_NAME` | No | `gemini-3.6-flash` | Model id |

## How to Run
```bash
python -m drafter octocat/hello-world --from v1.2.0 --to v1.3.0
```

## Example Input & Output
Run on `octocat/hello-world` between v1.2.0 and v1.3.0 (7 merged PRs) on 2026-10-20:
```
## Features
- Add dark mode toggle (#41)
## Fixes
- Fix crash when config file is empty (#44)
- Correct typo in CLI help (#45)
```
The run used about 1,900 input tokens and 150 output tokens.

## How to Test
`pytest` runs 14 tests against recorded GitHub and Gemini responses in `tests/fixtures`, so no keys or
network are needed. To check a live run, use the command above on any public repository with tags.

## Known Limitations
- PRs merged without a label all land under "Changes"; grouping depends on labels and titles.
- More than 300 PRs in one range are truncated to the newest 300.
- Tested on Windows 11 and Ubuntu 24.04; macOS is untested.

## Security & Privacy Considerations
- Keys are read from environment variables and never printed or logged.
- Only PR titles, numbers and labels are sent to Gemini; PR bodies and code are not.
- The tool makes read-only API calls and does not execute any code from the repository.

## Future Improvements
- [ ] Post the draft as a GitHub release (behind a confirmation prompt).

## License
Contributed under the repository's MIT license.

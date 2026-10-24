# Meeting Notes Action Agent

> Turn meeting notes into a concise summary, decisions, action items, and unresolved questions.

## Overview

### Problem Statement & Intended Users
- **Problem**: Meeting notes can make decisions and follow-up work difficult to find.
- **Intended Users**: Teams and individuals who want structured outcomes from plain-text notes.

### Key Features
- Extracts a concise summary and stated decisions.
- Lists action items with owners and due dates when present in the notes.
- Marks missing owners and dates as `null` instead of guessing.

## Technical Stack
- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Google Gen AI SDK
- **Models**: Gemini; defaults to `gemini-2.5-flash`
- **External APIs / Tools**: Google Gemini API

## Architecture & Data Flow

The CLI reads notes from a UTF-8 text file or standard input, sends them with an extraction prompt to Gemini, validates the returned JSON, then prints the normalized result.

## Prerequisites
- Python 3.10 or newer
- pip
- A Google AI Studio API key

## Installation & Setup

From this directory, create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your key to `.env` as the value of `GEMINI_API_KEY`. Never commit `.env` or share the key. You can optionally set `GEMINI_MODEL` to another available Gemini model.

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | None | Google AI Studio API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model used for analysis |

## How to Run

Analyze a text file:

```powershell
python main.py meeting.txt
```

Or pipe notes through standard input:

```powershell
Get-Content meeting.txt -Raw | python main.py
```

The result is JSON written to standard output. Errors are written to standard error and return a non-zero exit code.

## Example Input & Output

Example input:

```text
We agreed to publish the update Friday. Maya will prepare the release notes by Thursday.
We still need to decide whether the announcement goes to the full customer list.
```

Example output shape (wording can vary by model):

```json
{
  "summary": "The team plans to publish the update Friday.",
  "decisions": ["Publish the update Friday."],
  "action_items": [
    {
      "task": "Prepare the release notes",
      "owner": "Maya",
      "due_date": "Thursday"
    }
  ],
  "open_questions": ["Should the announcement go to the full customer list?"]
}
```

## How to Test

Run the unit tests without calling Gemini:

```powershell
python -m unittest discover -s tests -v
```

To verify the full API workflow, configure `GEMINI_API_KEY` and run the CLI with a short sample notes file.

## Known Limitations
- A valid Gemini API key and network access are required for analysis.
- Model wording and extraction can vary; review generated action items before relying on them.
- Dates are returned as written in the notes and are not resolved to calendar dates.

## Security & Privacy Considerations
- The API key is read from an environment variable or local `.env` file, which is ignored by Git.
- Meeting notes are sent to the Google Gemini API. Do not submit sensitive or confidential notes unless your data-handling requirements permit it.
- The agent only analyzes notes; it does not execute commands or perform external actions.

## Future Improvements
- [ ] Add support for exporting action items as CSV.
- [ ] Add an optional local-model provider.
- [ ] Add configurable output formats.

## License

This project is contributed under the repository's open-source license.
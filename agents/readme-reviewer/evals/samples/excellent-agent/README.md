# Note Summarizer

> Summarizes a plain-text file into three bullet points.

## Overview
This small agent reads a text file you point it at and returns a three bullet summary. It is meant for quick triage of long notes and meeting minutes.

## Technical Stack
- Python 3.11+
- requests 2.32 for the HTTP call to the summarizer service

## Architecture & Data Flow
The script reads the file, sends the text to the model endpoint, and prints the bullets it gets back. There is no state kept between runs.

## Prerequisites
- Python 3.11 or newer
- An API key for the summarizer service

## Installation & Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuration & Environment Variables
| Variable | Required | Description |
| :--- | :--- | :--- |
| `SUMMARY_API_KEY` | Yes | Key for the summarizer service |

## How to Run
```bash
python main.py notes.txt
```

## Example Input & Output
Input: a 40 line text file of meeting notes. Output:
```
- Launch moved to Friday
- Two bugs remain open
- Docs review is next week
```

## How to Test
Run `python main.py --self-check` and confirm it prints `ok`.

## Known Limitations
Files larger than 10 MB are rejected. The summary quality depends on the model and is not verified.

## Security & Privacy Considerations
The file text is sent to the summarizer service. The API key is read from the environment and never written to disk by the script.

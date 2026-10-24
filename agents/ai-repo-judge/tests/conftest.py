"""Test fixtures. Projects are written to tmp_path at runtime; fake secrets and injection phrases are
assembled from fragments so this repository never contains strings that look like real leaks."""

from __future__ import annotations

import random
import string
from pathlib import Path

import pytest

from judge.sources import local_workspace
from judge.workspace import Workspace


def fake_key(prefix: str, n: int, seed: int = 7) -> str:
    rng = random.Random(seed)
    return prefix + "".join(rng.choices(string.ascii_letters + string.digits, k=n))


def groq_key() -> str:
    return fake_key("gs" + "k_", 52)


GOOD_README = """# Meeting Summarizer

> Summarises meeting transcripts into decisions and action items.

## Overview
Busy teams lose decisions in long transcripts. This agent extracts decisions, owners and deadlines.

## Technical Stack
- Python 3.11, Google Gemini via google-genai, pydantic for structured output.

## Architecture & Data Flow
```
transcript -> prompt builder -> Gemini (JSON schema) -> validator -> markdown report
```

## Prerequisites
- Python 3.11+ and a Gemini API key.

## Installation & Setup
```bash
pip install -r requirements.txt
cp .env.example .env
```

## Configuration & Environment Variables
| Variable | Required | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | Gemini key |
| `MODEL_NAME` | No | Model to use |

## How to Run
```bash
python main.py --file samples/standup.txt
```

## Example Input & Output
### Input
```
Alice: let's ship on Friday. Bob will update the docs.
```
### Output
```
Decisions: ship Friday. Actions: Bob - update docs (due Fri).
```

## How to Test
```bash
pytest
```

## Known Limitations
- Transcripts over 50k characters are truncated before summarising, so very long meetings lose detail.

## Security & Privacy Considerations
- The key is read from the environment; transcripts are sent to Gemini and never stored locally.

## Future Improvements
- Speaker diarisation.

## License
MIT
"""

GOOD_MAIN = '''"""Meeting summarizer CLI."""
import argparse
import logging
import os

from google import genai
from pydantic import BaseModel

log = logging.getLogger(__name__)
MAX_CHARS = 50_000


class Summary(BaseModel):
    """Structured summary returned by the model."""

    decisions: list[str]
    actions: list[str]


def summarise(text: str, client=None) -> Summary:
    """Ask the model for a structured summary, retrying on transient errors."""
    client = client or genai.Client()
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=os.getenv("MODEL_NAME", "gemini-flash-latest"),
                contents=text[:MAX_CHARS],
                config={"response_mime_type": "application/json", "response_schema": Summary,
                        "max_output_tokens": 800, "system_instruction": "Extract decisions and actions."},
            )
            log.info("tokens used: %s", resp.usage_metadata)
            return Summary.model_validate_json(resp.text)
        except ValueError as exc:
            log.warning("attempt %d failed: %s", attempt, exc)
    raise RuntimeError("model failed")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--mock", action="store_true", help="mock mode: no API key needed")
    args = parser.parse_args()
    with open(args.file, encoding="utf-8") as fh:
        print(summarise(fh.read()))


if __name__ == "__main__":
    main()
'''

GOOD_TEST = """from unittest.mock import MagicMock

from main import summarise


def test_summarise_parses_json():
    client = MagicMock()
    client.models.generate_content.return_value.text = '{"decisions": ["ship"], "actions": []}'
    assert summarise("hi", client).decisions == ["ship"]


def test_truncates_input():
    client = MagicMock()
    client.models.generate_content.return_value.text = '{"decisions": [], "actions": []}'
    summarise("x" * 60_000, client)
    assert len(client.models.generate_content.call_args.kwargs["contents"]) == 50_000


def test_empty():
    client = MagicMock()
    client.models.generate_content.return_value.text = '{"decisions": [], "actions": []}'
    assert summarise("", client).actions == []
"""


def write_project(root: Path, category: str, slug: str, files: dict[str, str]) -> Path:
    folder = root / category / slug
    for rel, content in files.items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return folder


def good_files(**overrides: str) -> dict[str, str]:
    files = {
        "README.md": GOOD_README,
        "main.py": GOOD_MAIN,
        "tests/test_main.py": GOOD_TEST,
        "requirements.txt": "google-genai>=1.0,<2\npydantic>=2,<3\n",
        ".env.example": "GEMINI_API_KEY=your_key_here\nMODEL_NAME=gemini-flash-latest\n",
        ".gitignore": ".env\n.venv/\n",
    }
    files.update(overrides)
    return files


@pytest.fixture
def make_ws(tmp_path: Path):
    """make_ws(files, category="agents", slug="meeting-summarizer") -> Workspace for a local folder."""

    def _make(files: dict[str, str], category: str = "agents", slug: str = "meeting-summarizer") -> Workspace:
        return local_workspace(write_project(tmp_path, category, slug, files))

    return _make

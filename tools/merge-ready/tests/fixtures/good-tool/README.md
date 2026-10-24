# Good Tool Example

> A high-performance text token counter and context estimator for developers.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Developers building LLM applications need local, fast calculation of prompt token lengths without making remote API calls.
- **Intended Users**: Software engineers and prompt engineers designing AI workflows.

### Key Features
- Instant offline token estimation using regex heuristics.
- Support for plain text, markdown, and code files.
- Zero external runtime dependencies.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Vanilla Python Standard Library
- **Models**: N/A - offline utility
- **External APIs / Tools**: None

---

## Architecture & Data Flow

Reads local files or standard input, decomposes input text into approximate token boundaries, and outputs token counts and character statistics.

---

## Prerequisites

- Python 3.11 or later
- pip package manager

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/good-tool
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LOG_LEVEL` | No | `info` | Logging verbosity level |

---

## How to Run

```bash
python counter.py
```

---

## Example Input & Output

### Example Input
```
Hello world! This is a test prompt for token estimation.
```

### Example Output
```
Tokens estimated: 11
Characters: 55
```

---

## How to Test

```bash
pytest
```

---

## Known Limitations

- Uses heuristic whitespace and word boundary approximations rather than full BPE tokenization.
- Non-Latin multilingual token counts may deviate by up to 10% from proprietary model tokenizers.

---

## Security & Privacy Considerations

- Offline tool that processes all text locally in memory.
- No remote network requests or secret tokens required.
- No shell execution or dynamic eval performed.

---

## Future Improvements

- [ ] Add Tiktoken tokenizer binding.
- [ ] Support JSONL bulk file processing.

---

## License

This project is contributed under the repository's open-source license.

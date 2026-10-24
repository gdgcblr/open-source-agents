# Invoice Validation Agent

A lightweight Python tool that validates invoice data, detects duplicate invoices, and identifies incorrect totals using deterministic business rules.

## Overview

### Problem Statement & Intended Users
- **Problem:** Manual invoice checks can miss duplicate invoices, missing fields, and incorrect totals.
- **Intended Users:** Developers, accounts-payable teams, and AI automation builders.

### Key Features
- Required-field validation.
- Duplicate detection using invoice number and vendor.
- Subtotal, tax, and total verification.
- Structured JSON results with issue codes and severity.
- Automated tests and built-in demo scenarios.

## Technical Stack
- **Language & Runtime:** Python 3.10+
- **Core Library:** Standard Python library
- **Testing:** pytest
- **Models:** None required for core validation.
- **External APIs:** None.

## Architecture & Data Flow

```text
Invoice JSON
    |
    v
Required-field validation
    |
    v
Duplicate detection
    |
    v
Amount verification
    |
    v
Structured JSON report
```

## Prerequisites
- Python 3.10+
- pip

## Installation & Setup

From the repository root:

```bash
cd agents/invoice-validation-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration & Environment Variables

No environment variables or API keys are required.

## How to Run

```bash
python main.py --case valid
python main.py --case duplicate
python main.py --case mismatch
```

To validate a JSON file:

```bash
python main.py --input invoice.json
```

The input file must contain an `invoice` object and may include a `known_invoices` array.

## Example Input & Output

A valid invoice returns a result with `"status": "APPROVED"` and no issues.

A duplicate invoice or incorrect total returns `"status": "REJECTED"` with a specific issue code.

## How to Test

```bash
pytest -q
```

The test suite covers valid invoices, duplicate detection, total mismatches, and missing required fields.

## Known Limitations
- Accepts structured JSON only; PDF extraction is not implemented.
- Duplicate detection uses the supplied invoice list, not a database.
- Does not verify purchase orders against an external accounting system.
- An approved result means implemented checks passed; it is not authorization to pay.

## Security & Privacy Considerations
- Invoice data is processed locally.
- No external API calls are made.
- Never commit real invoices, credentials, or `.env` files.

## Future Improvements
- [ ] Optional Gemma-powered explanations.
- [ ] PDF invoice extraction.
- [ ] Purchase-order integration.
- [ ] Interactive web interface.

## License

This project is contributed under the repository's open-source license.
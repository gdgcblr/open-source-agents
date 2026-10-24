# FixProof

> An evidence-based civic complaint follow-up agent that helps residents document and escalate complaints marked as resolved when the reported problem persists.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Civic complaints (potholes, drainage, streetlights, etc.) are sometimes marked "resolved" by authorities while the underlying issue remains. Residents lack a structured way to document the discrepancy and generate a factual, verifiable escalation letter.
- **Intended Users**: Residents, civic activists, RTI applicants, ward-level representatives, and civic-tech platforms that need structured complaint-assessment data.

### Key Features
- **Structured complaint intake**: Accepts complaint reference, category, location, dates, authority status, resident follow-up observations, and supporting evidence descriptions.
- **Chronological timeline**: Builds a sortable timeline of all events with source classifications (user-supplied complaint/status vs. resident observation).
- **Discrepancy detection**: Flags cases where the authority status is "resolved" or "closed" but the resident reports the problem persists.
- **Missing-information flagging**: Identifies gaps such as missing resolution notes, status-update dates, or follow-up evidence.
- **Escalation letter generation**: Produces an editable, factual draft letter based solely on supplied information.
- **Epistemic honesty**: Clearly labels user-supplied complaint data, status updates, resident observations, and resident-described evidence. Never asserts that an authority acted improperly or that an issue physically persists without independent verification.
- **Offline-capable core**: The assessment engine (`fixproof_core.py`) uses only the Python standard library and requires no API keys or network access.
- **Streamlit Civic Dashboard**: An interactive local dashboard (`app.py`) with synthetic demo loading, side-by-side assessment results, editable escalation letter, and JSON download.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) v1.0+
- **Models**: Gemini 3.5 Flash Lite (configurable via `FIXPROOF_MODEL` environment variable)
- **UI Framework**: Streamlit
- **External APIs / Tools**: None required for core engine or UI. Pure Python stdlib + Streamlit.

---

## Architecture & Data Flow

```
[Structured Complaint Dict]
        │
        ▼
┌──────────────────────────┐
│   fixproof_core.py       │  ← Pure Python, no LLM, works offline
│   assess_complaint()     │
│   ┌────────────────────┐ │
│   │ validate_complaint │ │
│   │ build_timeline     │ │
│   │ analyse_status     │ │
│   │ generate_letter    │ │
│   └────────────────────┘ │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│   Structured Result      │  → timeline, flags, missing_info,
│   (Python dict / JSON)   │    escalation_letter, metadata
└──────────┬───────────────┘
           │
           ▼ (optional)
┌──────────────────────────┐
│   agent.py (Google ADK)  │  ← LLM-powered conversational wrapper
│   analyse_civic_complaint│    Calls core engine as a tool
│   tool                   │
└──────────────────────────┘
```

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or newer
- `pip` (Python package manager)
- A Google API key (only needed for the ADK agent; the core engine and tests work without one)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/fixproof
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate    # Linux/macOS
   # .venv\Scripts\activate     # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables (ADK agent only):**
   ```bash
   cp .env.example .env
   # Edit .env and add your GOOGLE_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Only for ADK agent | *None* | Google AI / Gemini API key |
| `FIXPROOF_MODEL` | No | `gemini-3.5-flash-lite` | Model identifier for the ADK agent |

The core engine and all unit tests work without any environment variables set.

---

## How to Run

### Core engine (no API key needed)

```python
from fixproof_core import assess_complaint

complaint = {
    "complaint_reference": "CMP-2026-04821",
    "issue_category": "Road Maintenance",
    "location": "MG Road, Ward 12, Bengaluru",
    "original_description": "Large pothole near bus stop causing traffic hazard.",
    "original_report_date": "2026-06-15",
    "authority_status": "resolved",
    "status_update_date": "2026-07-20",
    "resolution_note": "Pothole filled with cold-mix asphalt.",
    "followup_observation": "The patch has washed away; pothole is again visible.",
    "followup_observation_date": "2026-09-10",
    "supporting_evidence": [
        "Photo of pothole taken on 2026-09-10.",
        "Measurement showing depth of approximately 6 inches.",
    ],
}

result = assess_complaint(complaint)
print(result)
```

### Streamlit Civic Dashboard (Offline • No API key needed)

Run the local interactive dashboard:

```bash
cd agents/fixproof
streamlit run app.py
```

*Or from the repository root:*
```bash
streamlit run agents/fixproof/app.py
```

Features in the UI:
1. Click **📋 Load Demo (Pothole Complaint)** to instantly populate a complete synthetic complaint.
2. Click **🔍 Run Assessment** to compute the deterministic assessment.
3. Inspect the **Assessment Summary**, **Chronological Timeline**, **Discrepancy Flags**, **Missing Information**, and **Evidence Classifications**.
4. Review or edit the draft **Escalation Letter** directly in the text area.
5. Click **📥 Download Structured Assessment (JSON)** to save the evaluation results locally.

### ADK agent (requires GOOGLE_API_KEY)

```bash
# With google-adk installed and GOOGLE_API_KEY set:
adk run agents/fixproof
```

---

## Example Input & Output

### Example Input
```json
{
  "complaint_reference": "CMP-2026-04821",
  "issue_category": "Road Maintenance",
  "location": "MG Road, Ward 12, Bengaluru",
  "original_description": "Large pothole approximately 2 feet wide near bus stop causing traffic hazard.",
  "original_report_date": "2026-06-15",
  "authority_status": "resolved",
  "status_update_date": "2026-07-20",
  "resolution_note": "Pothole filled with cold-mix asphalt.",
  "followup_observation": "The patch has washed away after monsoon rains; the pothole is again visible and approximately the same size as originally reported.",
  "followup_observation_date": "2026-09-10",
  "supporting_evidence": [
    "Photo of pothole taken on 2026-09-10 showing exposed aggregate.",
    "Measurement showing depth of approximately 6 inches."
  ]
}
```

### Example Output (abbreviated)
```json
{
  "valid": true,
  "validation_errors": [],
  "timeline": [
    {"date": "2026-06-15", "event": "Complaint filed", "source": "user_supplied_complaint"},
    {"date": "2026-07-20", "event": "Authority status update", "source": "user_supplied_status"},
    {"date": "2026-09-10", "event": "Resident follow-up observation", "source": "resident_observation"}
  ],
  "analysis": {
    "authority_status_recorded": "resolved",
    "status_recognised": true,
    "resident_followup_provided": true,
    "flags": [
      "DISCREPANCY: The authority recorded the complaint as 'resolved', but the resident reports that the issue persists as of their follow-up observation. Independent verification is recommended."
    ],
    "missing_info": [],
    "evidence_notes": [
      {"index": 0, "description": "Photo of pothole...", "classification": "resident_described_evidence"}
    ]
  },
  "escalation_letter": "ESCALATION LETTER — DRAFT (EDITABLE)\n...",
  "metadata": {
    "source_classifications": {
      "user_supplied_complaint": "...",
      "user_supplied_status": "...",
      "resident_observation": "...",
      "resident_described_evidence": "..."
    },
    "disclaimer": "This assessment is generated from user-supplied data..."
  }
}
```

---

## How to Test

Run the full test suite (no API key required):

```bash
cd agents/fixproof
python3 -m pytest test_fixproof.py -v
```

The test suite covers:
- Resolved complaint with a reported persistent issue
- Resolved complaint without a follow-up observation
- In-progress complaint
- Missing required information (parametrized across all required fields)
- Timeline chronological ordering
- Supporting evidence indexing and unknown status handling
- Invalid inputs (wrong types, bad dates, malformed data)

---

## Known Limitations

- **No independent verification**: FixProof analyses user-supplied data only. It cannot verify whether an issue physically persists.
- **No photo/document analysis**: Supporting evidence is accepted as text descriptions only. Image or document processing is not implemented.
- **No persistence**: Complaints are assessed statelessly. There is no database or session memory.
- **Date-only granularity**: Timestamps are date-level (YYYY-MM-DD); time-of-day is not tracked.
- **English only**: The escalation letter and all labels are in English.
- **ADK agent requires API key**: The conversational agent layer requires a valid Google API key. The core engine works without one.
- **Tested on macOS and Linux**: Windows support is expected but not independently verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are loaded from environment variables via `python-dotenv`. The `.gitignore` excludes all `.env` files. No secrets are hardcoded.
- **Data Privacy**: When using the core engine, no data is transmitted externally — all processing is local. When using the ADK agent, complaint data is sent to the configured LLM provider (Google Gemini by default).
- **Safety**: FixProof does not execute shell commands, access the filesystem beyond its own directory, or perform any network requests (core engine). All example data is synthetic.

---

## Future Improvements

- [ ] Accept photo evidence and use vision models for basic verification.
- [ ] Add a simple web UI for complaint submission.
- [ ] Support multiple languages for escalation letters.
- [ ] Integrate with civic complaint portal APIs for automatic status lookup.
- [ ] Add persistence layer (SQLite) for complaint history tracking.
- [ ] Support batch assessment of multiple complaints.

---

## License

*This project is contributed under the repository's open-source license.*

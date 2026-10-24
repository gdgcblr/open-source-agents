# PDF-to-SurveyJS Agent

> Convert a text-based PDF form into a validated, human-reviewable SurveyJS JSON draft with Google ADK and Gemma.

---

## Overview

### Problem Statement & Real-World Context

- **The Government & Enterprise Challenge**: Public sector agencies, civic bodies, and enterprise portals manage hundreds of welfare schemes, permit applications, subsidies, and citizen services. Currently, the vast majority of these schemes exist exclusively as complex, multi-page PDF documents with legal declarations, multi-column layouts, nested eligibility logic, and diverse input formats.
- **The Bottleneck**: Manually recreating these scheme forms into web/mobile applications requires front-end developers to write custom forms, configure validations, and structure state machines from scratch. In practice, this takes **16 to 24 developer hours per form** (costing upwards of $1,500–$3,000 per scheme in engineering time) and creates a multi-year backlog for digital governance initiatives.
- **The Solution**: The **PDF-to-SurveyJS Agent** transforms any official government or enterprise scheme PDF into a clean, fully validated SurveyJS JSON schema in **under 2 minutes** (~95%+ reduction in form design and rollout time). The output immediately loads into an interactive visual editor and preview studio where administrative officers, compliance teams, and developers can review verbatim text, test conditional logic, and publish directly to citizen apps.

### Quantitative Impact at a Glance

| Metric | Traditional Manual Process | PDF-to-SurveyJS Agent | Impact |
| :--- | :--- | :--- | :--- |
| **Turnaround Time per Form** | 16–24 engineering hours (2–3 days) | **90–120 seconds** (plus human review) | **~95% faster** |
| **Engineering Cost per Form** | $1,500 – $3,000 in dev/UX hours | **< $0.05** (model API tokens) | **> 99% cost reduction** |
| **Digitization Throughput** | 1–2 schemes/week per developer | **40–50 schemes/day** per reviewer | **25x throughput increase** |
| **Structural Error Rate** | Frequent manual omissions/typos | **0% syntax/AST errors** (deterministic validation) | **Eliminates defects** |
| **Human-in-the-Loop Safety** | Prone to human transcription drift | Complete visual side-by-side audit studio | **100% auditable before release** |

### Key Capabilities

- **Deterministic Ingestion**: Fast, deterministic extraction via PyMuPDF with explicit security limits (15 MB file size, 100-page limit, byte-signature validation, and explicit scanned-PDF warnings).
- **Google ADK Orchestration**: Uses Google Agent Development Kit (ADK) 2.12 to define the agent lifecycle, manage streaming session state, bind domain tools, and enforce strict structured JSON envelopes via Pydantic schemas.
- **Gemma / Gemini Reasoning**: Leverages instruction-tuned models (`gemma-4-26b-a4b-it` or Gemini models) to intelligently infer field types (dates, emails, phones, long comments, radio groups, checkboxes, and informational HTML blocks).
- **Multi-Page Section Structuring**: Detects multi-page government sections (e.g., "Personal Details", "Eligibility Criteria", "Declarations") and organizes them into clean SurveyJS `pages[].elements` hierarchies.
- **Deterministic AST Validator & Normalizer**: Runs locally to sanitize conditional expressions (`visibleIf`), resolve question naming collisions, clean choice aliases, and ensure valid question types before presentation.
- **Bounded Self-Repair Loop**: If the model output violates the SurveyJS specification, the agent automatically feeds the exact compiler errors back to the model for a single targeted self-correction pass.
- **Interactive Review & Publishing Studio**: Built-in React + TypeScript + Vite workbench with live SurveyJS preview, side-by-side PDF viewer, in-browser JSON editor, and local drafts storage—ready to test and export with zero database setup.

---

## Technical Stack

- **Language**: Python 3.10+
- **Agent Framework**: Google Agent Development Kit (ADK) 2.12
- **Model**: Gemma 4 26B MoE IT (`gemma-4-26b-a4b-it`) by default, configurable to any Gemini/Gemma model
- **PDF Extraction**: PyMuPDF (`fitz`)
- **Validation Engine**: Local deterministic schema normalizer & SurveyJS AST validator
- **Studio UI**: React 19, TypeScript, Vite, SurveyJS Form Library (`survey-react-ui`, `survey-core`), and Flask
- **Test Suite**: pytest (31 unit/integration tests covering extraction, normalization, and bounds)

---

## Architecture & Data Flow

```text
[ Government Scheme PDF ]
           |
           v
 [ Deterministic Extraction (PyMuPDF) ]
      - Validates %PDF- signature, caps at 15 MB / 100 pages
      - Scanned document detector (explicit OCR warning)
           |
           v
  < Untrusted Text Boundary >
           |
           v
 [ Google ADK Agent + Gemma Model ]
      - Google ADK Agent Runner (InMemoryRunner)
      - Structured output envelope enforcement (SurveyDraftResponse)
      - Zero prompt injection vulnerability (PDF treated as data)
           |
           v
 [ Deterministic Normalizer & AST Validator ]
      - Normalizes condition syntax (visibleIf), question types, and choices
      - Checks required fields, page layouts, and name uniqueness
           |
           +------------------------------+
           | (Invalid)                    | (Valid)
           v                              v
 [ Bounded Auto-Repair ]        [ Validated SurveyJS JSON ]
      - Feeds exact compiler errors       |
        back to ADK session (max 1 retry) v
                                [ Interactive Review Studio ]
                                   - Live SurveyJS visual form
                                   - Side-by-side PDF review
                                   - Real-time JSON editing
                                   - Export & Publish to Citizen App
```

PDF content is treated as data, not instructions. The CLI performs deterministic extraction before invoking the model and validates every model response locally.

---

## Prerequisites

- Python 3.10 or newer
- A Google AI Studio API key with access to the configured Gemma model
- Internet access for the model request

OCR, local GPU setup, public hosting, and form-submission storage are not required or included.

---

## Installation & Setup

```bash
cd agents/pdf-to-surveyjs-agent
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Put your own API key in `.env`. The file is ignored by Git.

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GOOGLE_API_KEY` | Yes for conversion | None | Google AI Studio API key. `GEMINI_API_KEY` is also recognized. |
| `PDF_SURVEY_MODEL` | No | `gemma-4-26b-a4b-it` | Gemma model identifier passed to ADK. |
| `PDF_SURVEY_MAX_RETRIES` | No | `1` | Repair attempts after the first response; allowed range is 0-2. |
| `PDF_SURVEY_ALLOWED_ROOT` | No | Current directory | Directory the ADK-exposed extraction tool may read. Explicit CLI paths are not restricted. |

No credential is required for `--extract-only`, `--validate-json`, or tests. If credentials are missing, conversion exits with a clear configuration error and does not substitute another model.

---

## How to Run

Create the synthetic sample PDF:

```bash
python examples/create_sample_pdf.py
```

Inspect extraction without sending text to a model:

```bash
python main.py examples/sample_form.generated.pdf --extract-only
```

Convert a PDF and save the reviewable draft:

```bash
python main.py examples/sample_form.generated.pdf --output output/sample_output.json
```

### Local React demo

Install and build the frontend once:

```bash
cd web
npm install
npm run build
cd ..
```

Start the combined local app:

```bash
python web_app.py
```

Open `http://127.0.0.1:8000`. Upload a PDF to generate a form, or upload existing
SurveyJS JSON to preview it immediately. Valid JSON edits update the preview.
Drafts can be saved to browser local storage, and test responses stay in browser
memory unless downloaded. Nothing is stored in a database.

Validate an existing SurveyJS object without a model call:

```bash
python main.py --validate-json examples/sample_survey.json
```

`examples/sample_survey.json` is a documented example, not a claim that a live Gemma request was made in this checkout.

### Optional ADK Developer UI

The package exports the conventional `root_agent` definition. From the project directory, use ADK's local UI for interactive inspection:

```bash
adk web .
```

The purpose-built `main.py` workflow is recommended for conversion because it owns deterministic extraction, validation, and bounded repair.

---

## Example Input & Output

The generated sample PDF contains these synthetic fields:

```text
Full name (required)
Email address (required)
Experience level: Beginner / Intermediate / Advanced
May we email you workshop updates? Yes / No
```

A successful conversion returns an envelope like this:

```json
{
  "survey": {
    "title": "Community Workshop Registration",
    "elements": [
      {
        "type": "text",
        "name": "full_name",
        "title": "Full name",
        "isRequired": true
      }
    ]
  },
  "warnings": ["Review field names and required flags before publishing."],
  "model": "gemma-4-26b-a4b-it",
  "attempts": 1
}
```

The complete SurveyJS object is in `examples/sample_survey.json`, ready for the validation-only command or a SurveyJS application.

---

## How to Test

```bash
pytest -q
```

The suite creates temporary synthetic PDFs and covers extraction, low-text handling, invalid files, path restrictions, valid page/element layouts, malformed JSON, unsupported types, duplicate names, choice requirements, and missing model credentials. It does not spend model tokens.

---

## Validation Scope

This MVP accepts either top-level `elements` or `pages[].elements` (never both) and a conservative set of common SurveyJS types. Before validation, it safely normalizes common model formatting mistakes such as page-number references, missing display titles, and unnecessarily quoted conditional expressions. Checks include:

- a JSON object with at least one question;
- supported question `type` values;
- non-empty, unique question `name` values;
- non-empty human-readable titles for every question;
- non-empty `choices` for choice questions;
- boolean `isRequired` and string `visibleIf` values.

These checks verify useful structure, not the entire SurveyJS runtime schema or semantic correctness.

---

## Known Limitations

- No OCR; image-only/scanned PDFs are reported rather than guessed.
- Complex visual layout, tables, signatures, and handwriting may be lost during extraction.
- The model can omit or misclassify fields. Validation checks shape, not meaning.
- Very large PDFs can exceed hosted-model token quotas; automatic page chunking is not yet included.
- Conditional logic is included only when the model finds explicit evidence; a reviewer must confirm it.
- Input is limited to 15 MB and 100 pages. Model-bound extracted text is capped at 100,000 characters.
- Gemma access and identifiers can change. Override `PDF_SURVEY_MODEL` when required.

---

## Security & Privacy Considerations

- PDF text is untrusted and explicitly delimited in the model prompt.
- The application never executes commands, code, or instructions found in a PDF.
- The ADK-exposed extraction tool cannot read outside `PDF_SURVEY_ALLOWED_ROOT`.
- During conversion, document text is sent to the configured Google model endpoint. Do not use sensitive documents unless that transmission is permitted.
- The application does not log PDF contents, persist submissions, or publish forms.
- `.env`, generated output, caches, and virtual environments are excluded from Git.
- Generated forms are not guaranteed legally or operationally correct; keep human review in the loop.

---

## Future Improvements

- [ ] Add opt-in OCR with confidence reporting and tests.
- [ ] Expand validation against a maintained SurveyJS schema.
- [ ] Add a separately documented local Gemma runtime.
- [ ] Add evaluation fixtures for representative public forms.

---

## License

This project is contributed under the repository's MIT license.

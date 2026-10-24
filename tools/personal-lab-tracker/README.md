# Personal lab tracker

> A local dashboard for your own lab PDFs: sign in on this machine, confirm the extracted rows, and see each latest value on the interval printed with that result.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Lab results usually live in a portal or a paper PDF. Copying them into a third-party health app sends the report, and the name on it, somewhere else.
- **Intended Users**: A person keeping a private history of their own lab panels on one computer.

### Key Features
- Email and password sign-in stored on this machine. No confirmation mail is sent.
- Upload a digital PDF, then edit the table before it is saved. Flags are recalculated from the value and the reference interval on that report.
- With an extraction model selected, that model reads the PDF text as printed, including names and contact details. With none selected, a built-in reader handles the demo table layout and drops identifier lines.
- Latest results are meters. The green band is the printed interval, and the dot is the newest value. Changes sit on the same card.
- **More about these numbers** opens the stored rows and the changes as tables.
- An optional summary is a short paragraph. The model receives a fact sheet of analyte, value, unit, interval, flag, and collection date. A reply that is JSON, or that adds a number or an identifier, is discarded.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Local FastAPI app. Model calls are optional and use an OpenAI-compatible chat endpoint.
- **Models**: Each account picks Local or OpenAI, and a model name, separately for report extraction and summary generation. Suggested names in Settings are `gemma3`, `llama3.2`, and `qwen2.5` for Local, and `gpt-4.1-mini`, `gpt-4o-mini`, and `gpt-4o` for OpenAI. Any name matching the same pattern can be typed in.
- **External APIs / Tools**: OpenAI, only when a task is set to that provider. Otherwise SQLite, pypdf, and reportlab run on this machine, and Local talks to the base URL you enter.

---

## Architecture & Data Flow

```
[Sign in] --> [Empty dashboard]
                 |
                 +--> [PDF upload] --> [Extraction model, if selected, else built-in reader]
                 |                              |
                 |                              v
                 |                       [Editable table] --> [SQLite, per account]
                 |                                                    |
                 +--> [Load 3 fictional visits] ----------------------+
                                                                      |
                                                                      v
                                                         [Meters on the dashboard]
                                                                      |
                                                                      v
                                                    [Optional summary paragraph]
```

A selected extraction model receives the PDF text as printed. The summary model receives the fact sheet only, and must answer in plain sentences. Chat is not built.

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11 or newer
- pip
- An OpenAI API key only if you choose OpenAI in Settings. Enter it there. Do not put it in `.env`.
- A local model server only if you choose Local. It must speak the OpenAI chat API. Ollama’s default base URL is `http://127.0.0.1:11434/v1`.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/personal-lab-tracker
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Optional. If `SESSION_SECRET` is unset, the server writes `data/session.secret` on first launch and reuses it. The database defaults to `data/labs.sqlite`.
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `SESSION_SECRET` | No | A generated file `data/session.secret` | Signs the session cookie |
| `LAB_DB_PATH` | No | `data/labs.sqlite` | SQLite file for accounts, reports, results, model settings, and summaries |

Model choices and an OpenAI API key are saved per account from **Settings**. They live in the local database, not in `.env`. The key is not shown again after you save it. Local models use an OpenAI-compatible base URL, defaulting to `http://127.0.0.1:11434/v1`.

Leave an extraction model blank to use the built-in table reader. Leave a summary model blank to keep the dashboard on the meters alone.

---

## How to Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 . Create an account. The dashboard is empty until you upload a PDF or choose **Load demo record**. Open **Settings** to choose Local or OpenAI for extraction and for the summary.

The server listens on localhost only. Restart it after code changes. This command does not reload on its own.

---

## Example Input & Output

### Example Input
Load the fictional visits, or upload `fixtures/visit-1.pdf`. That file is a generated digital PDF whose header contains bait identifiers (`Demo User`, `00000 00000`, `demo.user@example.com`, `DEMO-0001`) and a results table:

```
Collected: 2025-11-02
Panel: Complete blood count
RESULTS
Test | Result | Unit | Reference interval | Flag
Hemoglobin | 12.4 | g/dL | 13.0-17.0 | L
```

The other two fixtures are `visit-2.pdf` (2026-02-18, CBC and lipids) and `visit-3.pdf` (2026-06-09, HbA1c, fasting glucose, LDL). Regenerate them with:

```bash
python -m app.pdfgen
```

### Example Output
After **Load demo record**, **Latest results** shows one meter per test. From a local run of the three fixtures:

- LDL cholesterol `138 mg/dL` is marked above the interval `<100` (2026-06-09), changed by `-4 mg/dL` since 2026-02-18.
- Triglycerides `160 mg/dL` is marked above `<150` (2026-02-18).
- Hemoglobin `13.6 g/dL` sits inside `13.0-17.0`, changed by `+1.2 g/dL` since 2025-11-02.

**More about these numbers** opens every stored row and those changes as tables. The bait name, phone, email, and record id are not in that table.

With no extraction model selected, the review screen for `visit-1.pdf` says identifier lines were removed and shows Hemoglobin `12.4` with flag `below` before you save. With a model selected, that file’s text, bait lines included, is sent to the provider you chose, and the review screen says so.

**Generate summary** asks the selected model for a paragraph. A reply that comes back as JSON, or that adds a number that is not on the fact sheet, is discarded and the meters stay as they are.

---

## How to Test

```bash
pytest
```

The suite covers PDF extraction, bait-identifier removal, meters, the fact sheet, account isolation, demo load, the upload-then-confirm path, Local and OpenAI extraction, grounded summaries, and rejection of a JSON summary.

Manual check:
1. Create an account at http://127.0.0.1:8000/register
2. Confirm the dashboard says there are no reports yet, with separate sections for adding a PDF and loading the demo
3. Load the demo record and read the meters
4. Open **More about these numbers** and confirm the rows are a table
5. Sign out, create a second account, and confirm that dashboard is empty and cannot open the first account’s report
6. In **Settings**, save Local or OpenAI for each task. The OpenAI key field stays empty after a reload, and the page says a key is saved

---

## Known Limitations

- With an extraction model selected, digital PDFs are read from their selectable text. The built-in reader, used only when no extraction model is selected, understands `Collected:`, `Panel:`, and pipe-separated `RESULTS` rows, which is the layout of the fixtures.
- Scanned pages and phone photos are not read. There is no OCR.
- Intervals are whatever was printed on that report. The app does not supply a clinical range of its own, and it does not convert units.
- A summary must be a paragraph. A reply that is JSON, or that adds a number or an identifier, is discarded. The meters are the record either way.
- Choosing OpenAI for extraction sends the PDF text, including names and contact details printed on it, to OpenAI. Choosing Local sends that same text to the base URL you entered. Summary calls send the fact sheet only.
- The meters and the summary describe numbers. They do not name a condition or suggest treatment. Chat is not built.
- The database file is not encrypted. Protection is the account password hash plus the machine's disk.
- There is no emailed password reset. Forgot-password is a local problem in this version.
- The app is meant for localhost. Putting it on a network would need HTTPS and a limit on sign-in attempts.
- A test name that itself contains an email, phone, or record-id pattern is refused at save time. A person's name typed into the test column would still be stored, which is why the confirm screen is there.

---

## Security & Privacy Considerations

- **Secrets Handling**: Passwords are stored as PBKDF2-SHA256 hashes. The session cookie is signed. Uploaded PDFs, the database, and `data/session.secret` live under `data/`, which is gitignored. The OpenAI key is stored in that database and is not written into `.env` or into a prompt. The repo ships no default password and no API key.
- **Data Privacy**: Account email and saved lab rows stay in local SQLite. When an extraction model is selected, the PDF text is sent to that provider as printed, including patient names, phones, emails, and record ids. The dashboard and the review screen say which provider receives it. Rows that still look like an email, phone, or record id are left out of the table. With no extraction model, identifier lines are dropped before the built-in reader stores rows. Summary calls receive the fact sheet only. The login email and the API key are not copied into prompts.
- **Safety**: The app does not run shell commands from the PDF. Uploads must start with `%PDF`, end in `.pdf`, and stay under 5 MB. Each account sees only its own rows.

---

## Future Improvements

- [ ] Chat over the fact sheet, still with no identifiers in the prompt.
- [ ] OCR for scanned reports.
- [ ] Encryption of the database file.

---

## License

*This project is contributed under the repository's open-source license.*

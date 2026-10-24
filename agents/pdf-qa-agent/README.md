# PDF Q&A Agent

> An interactive CLI agent that lets you ask natural-language questions about any PDF document using Google Gemini API.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reading through long PDF documents (research papers, reports, manuals, contracts) to find specific information is time-consuming and tedious.
- **Intended Users**: Students, researchers, developers, and professionals who frequently work with PDF documents and want instant, conversational access to their content.

### Key Features
- **Instant Answers**: Ask any question in plain English and get a precise answer from the PDF.
- **Multi-turn Conversation**: Maintains context from previous questions within the same session.
- **Simple CLI Interface**: No UI setup needed — just run and ask.
- **Safe & Local**: Your PDF content is sent to Gemini API only for processing; no data is stored.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework**: Vanilla Python (no heavy framework needed)
- **Model**: Google Gemini Flash Latest (via `google-genai` SDK)
- **PDF Parsing**: `pdfplumber`
- **External APIs**: Google Gemini API (free tier available)

---

## Architecture & Data Flow

```
[User provides PDF path]
        |
        v
[pdfplumber extracts text from PDF]
        |
        v
[User enters question in CLI]
        |
        v
[Gemini API: PDF text + question + chat history → answer]
        |
        v
[Answer printed to terminal]
        |
        v
[Loop: next question (with context from previous answers)]
```

---

## Prerequisites

- Python 3.10 or higher
- `pip` package manager
- A free Google Gemini API key → [Get one here](https://aistudio.google.com/apikey)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/pdf-qa-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # macOS/Linux:
   source .venv/bin/activate
   # Windows:
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key:**
   ```bash
   cp .env.example .env
   # Open .env and replace: GEMINI_API_KEY=your_actual_key_here
   ```

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Your Google Gemini API key |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model identifier |

---

## How to Run

```bash
# Basic usage
python main.py path/to/your/document.pdf

# Use a different Gemini model
python main.py report.pdf --model gemini-1.5-pro
```

---

## Example Input & Output

### Example Input
```
$ python main.py research_paper.pdf

Loading PDF: research_paper.pdf
   Reading 12 page(s)...
PDF loaded successfully! (4,231 words, 24,850 characters)

Model: gemini-2.5-flash
Ask any question about your PDF. Type 'quit' to exit.
============================================================

Your question: What is the main conclusion of this paper?
```

### Example Output
```
Thinking...

Answer:
The main conclusion of the paper is that transformer-based models
significantly outperform RNN-based architectures on long-document
summarization tasks, achieving a 12% improvement in ROUGE scores
while reducing inference time by 40% on the benchmark dataset.

------------------------------------------------------------

Your question: What dataset was used for evaluation?

Thinking...

Answer:
The paper used the CNN/DailyMail dataset for evaluation, consisting
of 287,113 training pairs and 13,368 test documents.

------------------------------------------------------------

Your question: quit
Goodbye!
```

---

## How to Test

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up .env with your API key
cp .env.example .env

# 3. Run with any PDF you have
python main.py any_document.pdf

# 4. Verify:
#    - PDF text is extracted and character count is shown
#    - Questions return relevant answers from the PDF
#    - "quit" exits cleanly
```

---

## Known Limitations

- **Image-based PDFs not supported**: Scanned or image-only PDFs cannot be processed (no OCR). Only text-based PDFs work.
- **Large PDFs truncated**: Only the first ~30,000 characters are sent to the API per query to stay within token limits.
- **No memory across sessions**: Conversation history is lost when the program exits.
- **Rate limits**: Free-tier Gemini API has rate limits; heavy usage may result in temporary throttling.
- **Tested on**: macOS and Linux. Windows support should work but is less tested.

---

## Security & Privacy Considerations

- **Secrets Handling**: API key is loaded from a `.env` file and never hardcoded. The `.env` file is excluded from Git via `.gitignore`.
- **Data Privacy**: PDF text is sent to Google's Gemini API for processing. Do not use this tool with confidential or sensitive documents unless you are comfortable with Google's data policies.
- **No Arbitrary Execution**: The agent does not execute shell commands or run arbitrary code.

---

## Future Improvements

- [ ] Add OCR support for scanned/image-based PDFs using `pytesseract`.
- [ ] Support multiple PDFs in one session.
- [ ] Add chunking strategy for very large PDFs (> 100 pages).
- [ ] Export Q&A session to a text/markdown file.
- [ ] Add a simple web UI using Gradio or Streamlit.

---

## License

This project is contributed under the repository's open-source license.

# Scholar-Agent

> An autonomous CLI research intelligence agent built with Google Agent Development Kit (ADK) and in-memory vector RAG to synthesize technical papers into structured insights, benchmark tables, and Mermaid system diagrams.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reading, synthesizing, and extracting verifiable architectural insights from dense machine learning preprints, systems papers, and technical whitepapers is time-consuming. Naive LLM summarization often hallucinations benchmark numbers, ignores hardware trade-offs, and remains vulnerable to adversarial prompt injections embedded inside PDF documents.
- **Intended Users**: AI Systems Engineers, Research Software Engineers (RSEs), Applied ML Scientists, and Technical Leads who need rapid, structured, and reproducible deconstructions of technical literature directly in their terminal.

### Key Features
- **In-Memory Vector RAG Search**: Chunks documents into overlapping semantic windows and builds an in-memory dense vector index using CPU-optimized sentence embeddings (`all-MiniLM-L6-v2`) without external vector database infrastructure.
- **Google ADK Agent Loop**: Employs Google Agent Development Kit (`google-adk`) `Agent` and `Runner` primitives to autonomously query the indexed context across methodology, evaluation metrics, and system trade-offs.
- **Strict Data Contracts & Artifact Export**: Uses Pydantic to enforce deterministic outputs, generating executive summaries, Rich terminal comparison tables, and syntactically valid Mermaid.js architecture diagrams exported as standalone files (`summary.md` and `architecture.mmd`).
- **Prompt Injection Defense**: Incorporates Unicode NFKC normalization and regex-based guardrails to neutralize adversarial prompt overrides (e.g., hidden instructions or system overrides) embedded in untrusted PDF or preprint text.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (Tested on Python 3.11 and 3.12)
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk`), Pydantic v2
- **Models**: Gemini 2.5 Flash (`gemini-2.5-flash`) via Google GenAI SDK; CPU Embeddings via `sentence-transformers/all-MiniLM-L6-v2`
- **External APIs / Tools / Libraries**: PyPDF, HTTPX (arXiv preprint streaming), Rich (CLI rendering), Click (CLI interface)

---

## Architecture & Data Flow

```text
[User CLI: URL / PDF / TXT] 
             │
             ▼
[Parser & Security Guardrails]  ──> Normalizes Unicode & strips prompt injections
             │
             ▼
[In-Memory Dense Vector RAG]   ──> Builds vector space via all-MiniLM-L6-v2
             │
             ▼
    [Google ADK Runner]        ──> Orchestrates autonomous reasoning loop
             │
             ├──> Calls Tool: `search_paper_context(query, top_k)`
             │
             ▼
[Gemini 2.5 Flash (Structured)]──> Enforces Pydantic schema contract
             │
             ▼
[Rich Console & Disk Exporter] ──> Outputs styled tables + exports summary.md & architecture.mmd
```

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10, 3.11, or 3.12 installed
- Package manager: `pip` or `uv`
- Google Gemini API Key (Obtain from [Google AI Studio](https://aistudio.google.com/))

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/scholar-agent
   ```

2. **Set up the virtual environment & install dependencies:**
   - Using standard Python `venv`:
     ```bash
     python3 -m venv .venv
     # Linux/macOS:
     source .venv/bin/activate
     # Windows:
     .venv\Scripts\activate

     pip install -r requirements.txt
     ```
   - Using `uv` (recommended for fast setup):
     ```bash
     uv venv --python 3.12
     source .venv/bin/activate
     uv pip install -r requirements.txt
     ```

3. **Configure Environment Variables:**
   Copy the example environment file and add your Gemini API key:
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Google Gemini API key required for ADK agent reasoning |
| `MODEL_NAME` | No | `gemini-2.5-flash` | ADK target model identifier (`gemini-2.5-flash`, `gemini-2.5-pro`) |
| `TOKENIZERS_PARALLELISM` | No | `false` | Disables tokenizer fork warnings on macOS/Linux |

---

## How to Run

Provide a remote arXiv URL, direct PDF URL, or local file path to the CLI:

```bash
# Analyze a paper directly from an arXiv URL:
python main.py https://arxiv.org/abs/2210.03629 --output-dir ./results

# Analyze a local PDF research paper:
python main.py ./sample_paper.pdf --output-dir ./results

# Run with a specific Gemini model:
python main.py https://arxiv.org/abs/2309.07597 --model gemini-2.5-pro --output-dir ./results
```

---

## Example Input & Output

### Example Input
```bash
python main.py https://arxiv.org/abs/2210.03629 --output-dir ./results
```

### Example Output
```text
✔ Ingestion Complete: Indexed 111 context passages from https://arxiv.org/pdf/2210.03629.pdf.
╭─────────────────────────────── ADK Executive Summary ────────────────────────────────╮
│ ReAct: Synergizing Reasoning and Acting in Language Models                           │
│ Authors: Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik Narasimhan│
│                                                                                      │
│ While Large Language Models excel at reasoning (Chain-of-Thought) and action         │
│ generation independently, ReAct interleaves reasoning traces ('thoughts') with       │
│ task-specific actions. This synergy allows dynamic action tracking, plan updates,    │
│ and grounding in external environments, significantly reducing hallucination rates.  │
╰──────────────────────────────────────────────────────────────────────────────────────╯

Key Technical Insights:
  1. Synergistic Interleaving: Reasoning traces guide tool execution while observations ground future thoughts.
  2. Hallucination Reduction: External tool observation injection prevents ungrounded parametric model drift.
  3. Bounded Context Utilization: Overcomes memory saturation through task-specific state tracking actions.

Table: Evaluation Benchmark Comparison (HotpotQA / Fever)
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Method                 ┃ HotpotQA (EM/F1) ┃ Fever (Acc)      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ Standard Prompting     │ 29.4 / 34.1      │ 56.3             │
│ Chain-of-Thought (CoT) │ 34.2 / 41.5      │ 62.1             │
│ ReAct (Ours)           │ 43.2 / 52.8      │ 81.4             │
└────────────────────────┴──────────────────┴──────────────────┘

Architecture Diagram (Mermaid.js):
flowchart TD
    A[Task Prompt] --> B[LLM Reasoning Trace: Thought]
    B --> C[Action Generation: Act]
    C --> D[External Tool / Environment Execution]
    D --> E[Observation Injection]
    E --> B
    E --> F[Final Output / Answer]

Exported artifacts successfully to: ./results/
```

---

## How to Test

### 1. Run Deterministic Unit Tests
Run the deterministic test suite verifying input sanitization, PDF parsing, and Pydantic schema validation:

```bash
pytest tests/
```

### 2. Run Empirical Model Evaluation Harness
Run the empirical evaluation benchmark verifying prompt injection defense and architectural concept recall:

```bash
python eval/run_eval.py
```

---

## Known Limitations

- **Context Window Ceiling**: Very long monographs (>80 pages) are budgeted to the first 45,000 characters during dense vector indexing to avoid excessive CPU memory overhead during embedding generation.
- **PDF Layout Extraction**: The default parser relies on `pypdf`; complex multi-column PDFs with embedded equations or non-standard fonts may experience occasional text order distortion.
- **Session Lifespan**: ADK sessions are maintained via `InMemorySessionService` and reset upon CLI termination. Long-term multi-paper conversational state is not persisted to disk.

---

## Security & Privacy Considerations

- **Secrets Handling**: API credentials are read strictly through environment variables (`GEMINI_API_KEY`) or `.env` files via `python-dotenv`. Credentials are never committed to version control or included in artifacts.
- **Data Privacy**: Document contents are embedded locally on CPU using `sentence-transformers` and only retrieved context chunks are transmitted over TLS to Google AI Studio for agent inference.
- **Safety & Injection Defense**: Untrusted text from PDFs and preprints undergoes Unicode NFKC normalization and regex sanitization to neutralize prompt injection vectors (`ignore previous instructions`, `system override`) before agent execution. The agent does not execute arbitrary local shell commands or untrusted code.

---

## Future Improvements

- [ ] Add offline local model execution via Ollama or vLLM (e.g., Gemma 2 / Llama 3.3).
- [ ] Implement layout-aware document chunking using `docling` or `pymupdf4llm` for superior table parsing.
- [ ] Integrate Mermaid CLI (`mmdc`) to automatically render `.mmd` files into visual `.png` diagrams alongside text summaries.

---

## License

This project is contributed under the repository's open-source license.
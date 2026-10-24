# Method Documents AI Agent

A lightweight documentation question-answering agent that searches a
local folder of engineering and developer documents, then uses the
Google Gemini API to produce concise answers grounded in retrieved
passages.

The project is designed as a small, reproducible MVP for exploring
document retrieval and AI-assisted knowledge access. It does **not**
download a local language model or embedding model.

> **Status:** Community MVP / sample project. Validate answers against
> source documents. This is not an approved engineering procedure or a
> replacement for controlled document systems.

## Features

-   Reads Markdown (`.md`), text (`.txt`), PDF (`.pdf`), and Word
    (`.docx`) files from a configured local folder.
-   Splits documents into overlapping text chunks and stores source
    filename and passage metadata.
-   Searches locally using lightweight lexical similarity; no embedding
    model is required.
-   Sends the question and selected excerpts to the Gemini API for
    answer generation.
-   Displays retrieved sources so users can verify the answer.
-   Provides both a Streamlit UI and a command-line interface.
-   Includes sample documents and offline unit tests for
    document/retrieval logic.

## How it works

1.  **Load documents:** Discover supported files in `KNOWLEDGE_DIR`.
2.  **Chunk:** Split extracted text into overlapping passages.
3.  **Index:** Save passage text and token data in a local JSON index.
4.  **Retrieve:** Rank passages against a question using lexical cosine
    similarity.
5.  **Generate:** Send the question and selected passages to Gemini,
    requesting citations such as `[S1]`.
6.  **Review:** Show the answer and source passages for verification.

See [Architecture](docs/ARCHITECTURE.md) for details.

## Requirements

-   Python 3.10 or newer.
-   Internet access to install Python packages and call the Gemini API.
-   A Google Gemini API key from [Google AI
    Studio](https://aistudio.google.com/apikey).
-   macOS or Linux commands below; Windows instructions have not been
    verified.

No Ollama installation or local model download is required.

## Quick start

Run commands from the `agents/method-docs-ai` directory.

### 1. Create a virtual environment and install dependencies

``` bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Configure the API key

``` bash
cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` to your own API key. Set
`GEMINI_CHAT_MODEL` to a model currently available to your Google AI
Studio/API account. Model availability and quotas can change.

**Never commit `.env`, API keys, private documents, or generated
indexes.**

### 3. Add documents and build the index

Place documents you are authorized to process under `knowledge_base/` or
update `KNOWLEDGE_DIR` in `.env`.

Supported extensions: `.md`, `.txt`, `.pdf`, `.docx`.

Build or refresh the index:

``` bash
python -m knowflow.cli index
```

### 4. Start the web application

``` bash
streamlit run app.py
```

Open the local URL printed by Streamlit, usually
`http://localhost:8501`. Use the UI to ask a question and inspect the
retrieved source passages.

### 5. Ask a question from the command line

``` bash
python -m knowflow.cli ask "What should I check before releasing a CAD drawing?"
```

### 6. Run tests

Use Python to invoke pytest so the active virtual environment is used
consistently:

``` bash
python -m pytest -q
```

Tests cover local document/retrieval helpers and do not require a live
Gemini API call. A passing unit-test suite does not guarantee that the
configured model or API quota is available.

## Configuration

  -----------------------------------------------------------------------
  Variable                Default                 Description
  ----------------------- ----------------------- -----------------------
  `GEMINI_API_KEY`        Required                Google AI Studio API
                                                  key. Keep it private.

  `GEMINI_CHAT_MODEL`     Set in `.env.example`   Gemini model used for
                                                  answer generation.
                                                  Choose one currently
                                                  available to your
                                                  account.

  `KNOWLEDGE_DIR`         `knowledge_base`        Directory containing
                                                  source documents.

  `INDEX_DIR`             `.knowflow_index`       Directory used for the
                                                  generated local index.

  `CHUNK_SIZE`            `1200`                  Approximate maximum
                                                  chunk size in
                                                  characters.

  `CHUNK_OVERLAP`         `180`                   Overlap between
                                                  adjacent chunks.

  `TOP_K`                 `5`                     Maximum number of
                                                  retrieved passages
                                                  considered.

  `MIN_RELEVANCE`         `0.08`                  Minimum lexical
                                                  similarity score used
                                                  to filter results; tune
                                                  with evaluation
                                                  questions.
  -----------------------------------------------------------------------

## Example questions

-   What should I check before releasing a CAD drawing?
-   Why might a drawing PDF show an outdated revision?
-   What metadata should be checked before submitting a drawing for
    review?
-   What should I check when an OData property is a collection?

Only ask questions covered by documents in the configured knowledge
folder. If the relevant information is absent or retrieval does not find
matching terms, the agent may not be able to answer.

## Security and privacy

-   Questions and retrieved document excerpts are sent to the Gemini
    API. Review the provider's current terms and your organization's
    policies before processing any non-public information.
-   Use synthetic, public, or explicitly approved documents for
    demonstrations.
-   The MVP reads a local folder; it is **not** a direct SharePoint
    connector.
-   It does not enforce SharePoint or other source-system access-control
    lists. Do not index documents with mixed permissions and assume the
    agent will preserve those permissions.
-   Do not commit API keys, `.env`, private documents, generated index
    files, or virtual environments.
-   Treat answers as assistance, not authority. Verify important
    information against the cited source material.
-   Retrieved document content is untrusted input. Prompt instructions
    mitigate prompt injection but cannot guarantee prevention.

See [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) and [Known
Limitations](docs/SECURITY_AND_PRIVACY.md#known-limitations).

## Troubleshooting

### `ModuleNotFoundError: No module named 'knowflow'`

Run commands from the project root and use:

``` bash
python -m pytest -q
python -m knowflow.cli index
```

### Gemini returns `404 NOT_FOUND`

Check that `GEMINI_CHAT_MODEL` is set to a model currently available to
your API account. Model names and availability can change; verify them
in Google AI Studio or the current Gemini API documentation.

### Gemini returns `503 UNAVAILABLE` or `429 RESOURCE_EXHAUSTED`

These errors can indicate temporary service demand or rate/quota limits.
Retry after a short delay, check your API usage and quota, and avoid
sending repeated requests in a tight loop.

### No documents found

Check `KNOWLEDGE_DIR`, ensure it exists, and confirm that it contains
supported file types with extractable text. Scanned PDFs may need OCR
before their content can be indexed.

## Project layout

``` text
method-docs-ai/
├── app.py
├── requirements.txt
├── .env.example
├── knowflow/
│   ├── agent.py
│   ├── cli.py
│   ├── config.py
│   ├── documents.py
│   ├── gemini_client.py
│   └── indexer.py
├── knowledge_base/
│   └── sample_docs/
├── evaluation/
│   └── sample_questions.json
├── tests/
└── docs/
```

The Python import package remains named `knowflow` for now; the
project/repository display name is **Method Documents AI Agent**.

## Dependencies

Dependencies are declared in `requirements.txt`. Do not add project
dependencies to the repository root. See the manifest for version
ranges.

## Contributing

Keep changes within `agents/method-docs-ai/` unless the repository's
contribution guide explicitly permits a project-index entry. Follow the
root contribution guide and shared README template. Run
`python -m pytest -q` before submitting a pull request. Do not include
secrets, generated indexes, virtual environments, or private source
documents.

## License

Use the license specified by the parent repository. If the repository
does not provide a clear license for this contribution, confirm the
expected license with maintainers before adding a separate license file.

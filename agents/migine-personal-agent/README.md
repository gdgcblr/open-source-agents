# migine-personal-agent

**Migine is an anagram of Gemini.**

A local Mac assistant for credit card bills, subscription spending, daily briefs,
Calendar, and Contacts. Built with uv, ADK 2.x, Gemma through Ollama, EmbeddingGemma,
and SQLite. App changes require approval. Contacts access is not yet working.

## Run locally

Requires macOS 14+, [uv](https://docs.astral.sh/uv/), and [Ollama](https://ollama.com/).
Open the Ollama app and keep it running. No cloud API key is needed.

**1. Set up the project** (from the repository root):

```sh
cd agents/migine-personal-agent
cp -n .env.example .env
uv sync --frozen
ollama pull gemma4:e4b
```

**2. Load the demo and start ADK Web:**

```sh
MIGINE_DATA_DIR=./demo uv run migine demo --month 2026-10
MIGINE_DATA_DIR=./demo uv run adk web examples/web --host 127.0.0.1 --port 8000 --max_llm_calls 8
```

**3. Open [ADK Web](http://127.0.0.1:8000)**, select `migine_web`, and ask:
“Summarise my bills and subscription spending for October 2026.”

Keep the terminal running; press **Ctrl+C** to stop. The financial demo uses synthetic
records and needs no Mac app access. ADK Web is for local development only.

For real email and Calendar access, follow [native setup and usage](USAGE.md#setup),
including Xcode Command Line Tools and `MIGINE_MAC_HELPER`. Import and review email
records, then start the same Web command with `MIGINE_DATA_DIR=./data`.
App tools access your real Mac; approve changes from the terminal using the same data
directory. Chat history is stored separately in ignored `.adk/` folders under `examples/web/`.
EmbeddingGemma is optional for search; its setup is in [USAGE.md](USAGE.md).

## Components

```mermaid
flowchart TB
    subgraph MAC["Your Mac — local processing"]
        direction TB
        Web["ADK Web<br/>localhost:8000"]:::ui
        CLI["Terminal CLI"]:::ui
        Agent["Migine<br/>ADK agent"]:::agent

        subgraph LOCAL["Local models and storage"]
            Gemma["Ollama · Gemma<br/>Reasoning and extraction"]:::model
            Reports["Financial reports<br/>and search"]:::agent
            DB[("SQLite<br/>Evidence · memory · vectors")]:::store
            Embed["EmbeddingGemma<br/>Optional search"]:::model
        end

        subgraph NATIVE["Mac app access"]
            Connector["Mac connector"]:::native
            Apps["Mail · Calendar<br/>Contacts: permission issue"]:::native
            Approval{"Approve exact<br/>app change?"}:::approval
        end

        Web --> Agent
        CLI --> Agent
        Agent <--> Gemma
        Agent --> Reports
        Reports <--> DB
        CLI --> Embed
        Embed <--> DB
        Agent -- Read --> Connector
        Agent -- Save proposals --> DB
        CLI -- Apply request --> Approval
        Approval -- Approved --> Connector
        Connector --> Apps
    end

    classDef ui fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef agent fill:#ede9fe,stroke:#7c3aed,color:#4c1d95
    classDef model fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef store fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef native fill:#f1f5f9,stroke:#64748b,color:#0f172a
    classDef approval fill:#ffedd5,stroke:#ea580c,color:#7c2d12
```

## Tests and limits

Tested only on macOS. Linux and Windows are untested; the Mac app connectors require macOS.
Run `uv run pytest -q`. See [test results](TESTING.md) for validation and open issues.
Mail scans can be incomplete. Financial records require review. Real bill totals and
Docker image execution remain unverified.

## Privacy

Gemma and EmbeddingGemma run locally through Ollama; no hosted model API is required.
Cached email, memory, search vectors, and chat history stay in local storage until deleted.
Private data is excluded from Git, but SQLite is not encrypted by this app. Protect your
Mac and backups. Initial dependency and model downloads require internet access.
Keep ADK Web on localhost. See [privacy and data deletion](USAGE.md#privacy-and-limits).

[Commands, Docker, and privacy](USAGE.md) · [Contributing](../../CONTRIBUTING.md)

Keep contributions inside this project folder. Never commit credentials or personal data.
The repository MIT license applies.

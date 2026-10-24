# Open Source Scout Agent

> An autonomous open-source discovery and mentoring agent that finds, ranks, and summarizes the top 15 GitHub repositories tailored to your chosen tech stack and complexity level, enforced with strict anti-hallucination guardrails.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Finding active, high-quality open-source projects suitable for a developer's specific skill level is overwhelming. Searching GitHub manually yields thousands of abandoned repositories, monolithic architectures unsuited for beginners, or confusing setups without clear onboarding pathways. Furthermore, when asking general LLMs for repository recommendations, they frequently hallucinate dead links, outdated libraries, or non-existent projects.
- **Intended Users**: Open-source contributors, students, and engineers looking for curated repositories to study, practice with, or contribute to based on exact language/framework and difficulty preferences.

### Key Features
- **Multi-Signal Filtering (Step 1)**: Filters by tech stack, target experience level (`beginner`, `intermediate`, `advanced`), and contribution scope (Small Scope / Good First Issues, Documentation, Bug Fixes, Core Features).
- **Repository Health & Contributor Scoring**: Computes a transparent 0-100 health score based on push recency, documentation completeness, issue engagement, and community activity.
- **Maintainer Responsiveness Summaries**: Classifies maintainer engagement into bounded response tiers (e.g., reviews within 48 hours vs weekly cycles).
- **Contribution Readiness Classification**: Grades repositories (Tier 1: Documented & Starter Friendly, Tier 2: Standard, Tier 3: Self-Guided) to guide contributors to well-maintained projects.
- **Gemini Problem & Learning Summarizer (Step 2)**: Uses Google Gemini to distill the real-world engineering problem each project solves, key architectural concepts, and suggested first steps.
- **Strict Whitelist Guardrails (Step 3)**: Validates every LLM response against an immutable whitelist of authentic Step 1 GitHub API results. Any hallucinated repository is caught and rejected immediately.
- **Direct 1-Click Forking**: Signed-in users can fork any selected repository directly to their personal GitHub account via the GitHub REST API.
- **User Activity Dashboard**: Displays the signed-in user's public GitHub pull request and issue contribution history.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Custom modular agent pipeline with strict data contracts
- **AI Models**: Google Gemini (`gemini-2.5-flash` via `google-genai` / `google-generativeai`)
- **APIs & Protocols**: GitHub REST API v3
- **Data Validation & Guardrails**: In-memory whitelist verification & schema validation
- **Output Artifacts**: Structured JSON (`top_15_repos.json`, `summarized_repos.json`) and responsive HTML dashboard (`report.html`)

---

## Architecture & Data Flow

```
[User Input: Tech Stack & Complexity]
                 │
                 ▼
     ┌───────────────────────┐
     │  GitHub Scout Client  │ (Step 1: Queries GitHub REST API)
     └───────────┬───────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │   Composite Ranking   │ (Ranks by stars, activity decay, issues)
     └───────────┬───────────┘
                 │
                 ▼
       [top_15_repos.json]
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
┌──────────────┐   ┌───────────────────────────┐
│ Whitelist    │   │ Gemini LLM Summarizer     │ (Step 2: Problem statement,
│ Guardrail    │   └─────────────┬─────────────┘          learning values)
└──────┬───────┘                 │
       │                         ▼
       │             [Raw Candidate Summaries]
       │                         │
       └─────────────────────────┼────────────────────────┐
                                 ▼                        ▼
                   ┌───────────────────────────┐    [Violation Blocked]
                   │ Whitelist Verification    │───► (Raises error on
                   │ (Enforces 0 Hallucinations│     hallucinated repos)
                   └─────────────┬─────────────┘
                                 │
                                 ▼
                     [summarized_repos.json]
                                 │
                                 ▼
                      [Navigable report.html]
```

---

## Prerequisites & Authentication

- Python 3.10 or higher.
- A modern web browser for the optional local dashboard.
- **Explicit GitHub Login**:
  - The web dashboard starts as `Not Logged In` by default.
  - Clicking `🔑 Log in with GitHub` allows signing in via your Personal Access Token.
  - Once logged in, you can fork any project directly to your account with 1 click, or click `Log out` to switch accounts.
- **Gemini API Key**:
  - Optional. Read from the environment or `.env`; metadata-only summaries are used when it is not configured.

---

## Where to Add Your LLM API Key

To configure your API keys for all future runs:

1. In the agent folder, copy the `.env.example` file to `.env`:
   ```bash
   cd agents/open-source-scout
   cp .env.example .env
   ```

2. Open `.env` and paste your Gemini API key:
   ```ini
   # Google Gemini API Key (from https://aistudio.google.com/apikey)
   GEMINI_API_KEY=AIzaSyYourGeminiApiKeyHere

   # Optional GitHub Personal Access Token (if not using GitHub CLI)
   GITHUB_TOKEN=ghp_YourOptionalTokenHere
   ```

> [!NOTE]
> The `.env` file is already listed in `.gitignore`. It is stored locally on your machine and will **never** be committed or leaked to GitHub.

---

## Installation & Setup (Using a Virtual Environment)

It is strongly recommended to run this agent inside an isolated Python virtual environment (`venv`) to avoid package conflicts with your system Python.

### Step 1: Navigate to the agent directory
```bash
cd agents/open-source-scout
```

### Step 2: Create the virtual environment
Create a virtual environment named `.venv`:
```bash
# On macOS / Linux:
python3 -m venv .venv

# On Windows:
python -m venv .venv
```

### Step 3: Activate the virtual environment
Before installing packages or running the agent, activate the environment:

* **macOS / Linux (zsh, bash)**:
  ```bash
  source .venv/bin/activate
  ```
* **Windows (PowerShell)**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
  *(If you encounter execution policy restrictions on Windows, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)*
* **Windows (Command Prompt / cmd.exe)**:
  ```cmd
  .venv\Scripts\activate.bat
  ```

> [!TIP]
> When active, your terminal prompt will show the `(.venv)` prefix, confirming that Python commands are isolated to this environment.

### Step 4: Install dependencies
With `.venv` active, install the required packages:
```bash
pip install -r requirements.txt
```

### Step 5: Configure Environment Variables
Copy the example configuration:
```bash
cp .env.example .env
```
Edit `.env` to provide your Gemini API key (and optionally a GitHub token):
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GITHUB_TOKEN=your_github_token_here
```

### Deactivating the Virtual Environment
When you are done using the agent, you can exit the virtual environment by running:
```bash
deactivate
```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GITHUB_TOKEN` | No | *None* | GitHub Personal Access Token (PAT) for authenticated search |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key for generating problem summaries |
| `FLASK_SECRET_KEY` | No | Random per process | Stable random Flask signing key; set explicitly for deployments |
| `HOST` | No | `127.0.0.1` | Bind address; keep local unless deployment networking is secured |
| `PORT` | No | `5050` | Local dashboard port |
| `DEFAULT_TECH_STACK` | No | `python` | Default programming language or framework keyword |
| `DEFAULT_COMPLEXITY` | No | `beginner` | Default difficulty level (`beginner`, `intermediate`, `advanced`) |
| `TOP_N_REPOS` | No | `15` | Number of repositories to fetch and rank |

---

## How to Run

> [!NOTE]
> Ensure your virtual environment is active (`source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\activate` on Windows) before running these commands.

### 🌟 Option 1: Web Frontend (Recommended)
Launch the interactive web UI to search GitHub by tech stack, contributor level, and contribution scope:
```bash
python3 app.py
```
Open **[http://localhost:5050](http://localhost:5050)** in your browser. 
- Features dropdowns for all popular languages and frameworks.
- Uses Gemini summaries when `GEMINI_API_KEY` is configured; otherwise it uses repository metadata.
- Shows the signed-in GitHub account and its public issue and pull request activity.
- Includes 1-click `git clone` copy buttons and instant links to Good First Issues.

---

### Option 2: CLI Terminal Mode

#### 1. Step 1 Only (Fetch & Rank Top 15 Repositories to JSON)
```bash
python3 main.py --tech-stack python --complexity beginner --step 1
```

### 2. Full Pipeline with Gemini Summarization (Steps 1, 2 & 3)
```bash
python3 main.py --tech-stack typescript --complexity intermediate
```

### 3. Full Pipeline without LLM (Fast Mode using GitHub descriptions)
```bash
python3 main.py --tech-stack rust --complexity beginner --skip-llm
```

### 4. Interactive Mode
Simply run without arguments to be prompted:
```bash
python3 main.py
```

---

## Example Output

### 1. Top 15 JSON Schema (`top_15_repos.json`)
```json
{
  "meta": {
    "tech_stack": "python",
    "complexity": "beginner",
    "count": 15,
    "generated_at": "2026-10-24T08:01:51Z"
  },
  "repositories": [
    {
      "rank": 1,
      "score": 3187.7,
      "id": 1054512829,
      "name": "vllm-omni",
      "full_name": "vllm-project/vllm-omni",
      "html_url": "https://github.com/vllm-project/vllm-omni",
      "clone_url": "https://github.com/vllm-project/vllm-omni.git",
      "description": "A framework for efficient model inference with omni-modality models",
      "language": "Python",
      "stars": 7331,
      "forks": 1959,
      "open_issues_count": 1841,
      "topics": ["multimodal", "inference", "pytorch"],
      "good_first_issues_url": "https://github.com/vllm-project/vllm-omni/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22"
    }
  ]
}
```

### 2. Interactive Navigable Page (`report.html`)
The agent produces a responsive web dashboard with:
- Top 15 ranked repository cards.
- Problem statements and learning values.
- Direct links to GitHub and filtered Good First Issues.
- Click-to-copy `git clone` snippets.

---

## How to Test

Run the automated suite for guardrails, GitHub credential handling, and report rendering:

```bash
python -m unittest -v test_guardrails test_app_auth test_report_safety
```

All six tests should pass.

### Environment Verification

- **Reproducible setup**: Installed `requirements.txt` in a fresh Python 3.13 virtual environment and ran the full six-test suite successfully.
- **Core functionality**: A live GitHub search and the end-to-end metadata fallback flow completed successfully, including JSON and HTML report generation. The live Gemini API path was not exercised.

---

## Known Limitations

- GitHub API rate limits apply, especially when searching without a token.
- GitHub login sessions are held in process memory. Restarting the app signs users out, and multi-process deployments need a shared server-side session store.
- The repository whitelist verifies repository identity, not the factual accuracy of Gemini-generated summaries.
- Gemini summaries require a configured API key and may incur provider usage costs.

---

## Security & Privacy Considerations

- **Anti-Hallucination Guardrails**: Step 3 enforces a strict in-memory whitelist created from authentic GitHub API results. If the LLM generates any repository not present in the pre-verified dataset, it is immediately blocked.
- **Token Handling**: GitHub tokens remain in server memory; the browser cookie contains only a random session identifier. Sessions are cleared on logout or process restart.
- **Zero Committed Secrets**: `.env`, virtual environments, and generated reports are ignored. Only `.env.example` with placeholders is committed.
- **Report Rendering**: External repository text is HTML-escaped, and generated report links are restricted to HTTPS URLs on `github.com`.
- **Local Binding**: The dashboard listens on `127.0.0.1` by default. Set a stable random `FLASK_SECRET_KEY` and use secured HTTPS networking before exposing it beyond the local machine.

---

## Future Improvements

- [ ] Support GitHub GraphQL API for batch metrics (e.g. contributor count and PR merge velocity).
- [ ] Add configurable session expiration and a shared session store for multi-process deployments.
- [ ] Add email or Discord notification digest for newly trending starter repos.

---

## License

This project is contributed under the repository's open-source MIT license.

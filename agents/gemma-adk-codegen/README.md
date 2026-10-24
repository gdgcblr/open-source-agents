# Gemma ADK Code Generation Team

> A local-first multi-agent application that turns a software problem statement into a task plan, generated project files, independent review, and a test plan.

## Project Overview

Starting from a broad software requirement involves breaking it into manageable work, producing an initial project structure, and checking the implementation plan. This project provides a Streamlit interface and command-line runner for that workflow, using Google Agent Development Kit (ADK) with Gemma served by Ollama.

The intended users are developers who want a reviewable starting point for a new application or feature. The generator is not an autonomous coding environment: it writes generated files into an isolated artifacts folder, but does not inspect an existing repository, change this repository, execute generated code, or run generated tests.

### Features

- A planner converts the problem statement into ordered tasks with acceptance criteria.
- Before task agents start, a planner checkpoint can ask targeted clarification questions, incorporate the user's answers, and present a proposed task plan for approval.
- For each task, coding, review, and test-planning agents work concurrently; a final synthesis agent integrates all results into the project structure.
- A Streamlit UI displays the problem, task plan, generated source/configuration/tests, review feedback, and test plans. It supports individual-file and project ZIP downloads.
- During generation, the UI shows a live agent tree with the active planner, coder, reviewer, or test planner highlighted, plus completed, waiting, or failed states for each task.
- A CLI is available for running the workflow without the UI.
- Ollama and its models remain on the host. Docker is used only for the Streamlit application.
- Input, response, task-plan, and generated-file limits plus path validation provide deterministic safety boundaries.

## Architecture

```text
Problem statement
     |
     v
 Planner agent --> validated task-plan.json
     |
     +--> For each task, in order:
          Coding agent --> project/<source, tests, config, docs>
              |         (the project tree is context for later tasks)
              +--> Reviewer agent --> review.md
              +--> Testing agent  --> test-plan.md
     |
     v
 Streamlit artifact browser / CLI output
```

The planner runs first. Then each task starts three independent agents concurrently: coder, reviewer, and test planner. A UI setting limits how many task groups run at once (1–4) for local hardware capacity. Each coder writes an isolated proposal; reviewers and test planners work from the task requirements because they start at the same time and do not wait for the coder. After every task agent completes, a synthesis agent receives all proposals and reports, resolves overlap, and writes the final integrated project under `project/`. ADK manages the model-agent invocations, and LiteLLM connects ADK to Ollama's OpenAI-compatible chat endpoint.

## Requirements

### Docker Setup

- Docker Desktop with Docker Compose v2, running and ready.
- Ollama installed and running on the host computer.
- A local Ollama model installed, such as `gemma3:latest` or `gemma2:9b`.
- Network access from Docker Desktop to the host Ollama API on port `11434`.
- Several gigabytes of free disk space for the application image and local model. The model is not copied into Docker.

### Direct Python Setup

- Python 3.10 or newer (the Docker image uses Python 3.12).
- `pip` and `venv`.
- Ollama running on the same host, with a local model already pulled.

## Complete Setup with Docker and Make

Docker is the recommended setup. Run the following from this directory (`agents/gemma-adk-codegen`).

1. Start Docker Desktop and Ollama.
2. Confirm the model is installed and note its exact tag:

   ```bash
   ollama list
   ```

   If needed, install one locally:

   ```bash
   ollama pull gemma3
   ```

3. Make sure the Ollama API can accept connections from Docker Desktop. On macOS, Docker can address the host as `host.docker.internal`. If Ollama is listening only on loopback, quit the Ollama desktop app and start the server with:

   ```bash
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ```

   Keep this API limited to a trusted local machine/network and apply firewall rules. Ollama's API does not include authentication by default.

4. Copy the example configuration and start the application:

   ```bash
   cp .env.example .env
   make up
   ```

5. Open the URL printed by Make, usually [http://localhost:8501](http://localhost:8501). If that port is busy, Make selects the next available port.

`make up` checks the host Ollama API and requested model tag before building and starting the Streamlit container. It does **not** start an Ollama container or download models into Docker. The host preflight connects to `OLLAMA_API_BASE` (default `http://localhost:11434`); from inside Docker Compose, the application connects to `http://host.docker.internal:11434`.

### Make Commands

| Command | Description |
| :--- | :--- |
| `make up` | Check local Ollama/model, build the app image, and start Streamlit; select an available port starting at 8501. |
| `make check-ollama` | Check that the configured host Ollama API and model tag are available. |
| `make status` | Show the Compose app container status and health. |
| `make logs` | Follow the app container logs. |
| `make stop` | Stop the app container without removing it. |
| `make down` | Stop and remove the app container and Compose network. Artifacts and host models are preserved. |
| `make config` | Render the resolved Compose configuration. |

Choose another model already installed on the host:

```bash
make up OLLAMA_MODEL_TAG=gemma2:9b
```

Choose a preferred UI port (Make searches upward if it is occupied):

```bash
make up APP_PORT=8510 OLLAMA_MODEL_TAG=gemma3:latest
```

Generated runs persist under `artifacts/` on the host. The Docker image and Compose stack do not mount or modify your source repository beyond this artifacts directory.

## Direct Python Setup

Use this mode if you do not want to run the application in Docker. Ollama and Python both run directly on the host.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

For the default model, ensure Ollama has `gemma3:latest` installed. In `.env`, set:

```dotenv
OLLAMA_API_BASE=http://localhost:11434
MODEL_NAME=ollama_chat/gemma3:latest
```

Then start the UI or use the CLI as described below. Do not commit `.env`; it is excluded by `.gitignore`.

## Configuration

| Setting | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `OLLAMA_MODEL_TAG` | `gemma3:latest` | Make preflight / Docker selection | Exact model tag from `ollama list`; override on the Make command line. |
| `MODEL_NAME` | `ollama_chat/gemma3:latest` | ADK / LiteLLM | LiteLLM model identifier. In Docker, Make derives this from `OLLAMA_MODEL_TAG`; the Streamlit sidebar can also choose the model. |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Host preflight / direct Python | Host Ollama API URL. In Compose the app reaches the host through `host.docker.internal:11434`. |
| `APP_PORT` | `8501` | Make / Docker Compose | Preferred host port for Streamlit. Make selects the next available port if necessary. |

For other LiteLLM-compatible model providers, configure the appropriate credentials and model identifier. Provider credentials must not be committed. Ollama on the host is the default and requires no API key.

## Using the Application

### Streamlit UI

Docker mode launches the UI with `make up`. In direct Python mode, activate `.venv` and run:

```bash
streamlit run app.py
```

Enter a problem statement with the desired behavior, constraints, and target language. Choose the model, maximum task count, and number of parallel task groups in the sidebar, then select **Generate project**. The planner may pause to ask up to five focused questions; answer them and choose **Update task plan**. There are at most two clarification rounds. The planner then shows a proposed plan for human approval before any task agents run. If details remain unspecified at the limit, it is instructed to proceed with conventional assumptions. During generation, the live agent tree highlights active agents and shows the final synthesis stage. Choose an artifact run and task to inspect the plan, independent task proposals, reviewer feedback, and test plan. The **Final project** tab shows the integrated output and can download one file or the whole project as a ZIP.

### Command Line

Run from this directory with the virtual environment active and Ollama available:

```bash
python main.py "Build a command-line habit tracker with recurring reminders and a local SQLite database"
```

Specify a task limit and output directory:

```bash
python main.py "Add CSV import and validation to the application" --output ./artifacts --max-tasks 5
```

`--max-tasks` accepts values from 1 through 20 and defaults to 8.

## Generated Artifacts

Each run creates a unique directory under `artifacts/`. The planner derives a concise project name from the original request and clarification answers; it is used as the directory prefix and UI label. A timestamp and short unique suffix keep repeated projects distinct:

```text
artifacts/todo-list-application-20261024T093514Z-3568c3a9/
├── task-plan.json
├── project/
│   ├── README.md
│   ├── pyproject.toml
│   └── src/                 # Example; files depend on the request
├── task-001-<task-name>/
│   ├── proposal/            # Isolated output from this task's coder
│   ├── generated-files.json
│   ├── implementation.md    # Proposal file list
│   ├── review.md
│   └── test-plan.md
└── task-002-<task-name>/...
├── project/                 # Final synthesis output, not individual proposals
├── final-files.json
└── synthesis.md
```

The `project/` directory is produced after all task-agent outputs are available. Every final project includes a `README.md` with its overview, requirements, setup, run, test, and project-structure instructions; if synthesis omits an adequate README, the workflow creates one using the user request, clarification answers, and generated manifests. The workflow performs syntax-only checks on generated Python, JSON, TOML, and YAML where supported and records findings in `static-checks.md`. It does not execute generated code, install generated dependencies, or run generated tests.

Normally the synthesis agent integrates task proposals. If model synthesis and its single format-repair attempt both fail, the workflow creates a deterministic merge of validated task proposals and records a warning in `synthesis.md`. The first task's version is kept at the shared path; differing later versions are preserved beneath `project/task-proposals/<task-id>/` and listed in the report rather than causing the run to fail or silently overwriting a file. Review those alternatives and integrate them as needed: this fallback is not equivalent to model-based synthesis. Task folders contain independent proposals and their review/test-planning artifacts. Generated files remain isolated under the run directory; they are not applied to the agent repository and are not automatically executed.

Older runs created before project naming was added may still appear with their original timestamp-only names.

## Development and Tests

The tests validate planner clarification parsing and answer feedback, task-plan parsing and repair, prompt data boundaries, generated file manifest validation, path traversal protection, project README generation, static syntax checks, artifact writing, parallel execution ordering, synthesis fallback, and agent progress rendering. They do not require Ollama or an API key:

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py main.py workflow.py progress_ui.py scripts/check_ollama.py scripts/find_free_port.py
```

Validate Docker's resolved configuration:

```bash
make config
```

## Current Issues and Future Work

The current version is a local-first prototype. The items below are known gaps and potential follow-up contributions; they are not implemented yet. The first item is the main persistence challenge for future development.

### 1. Replace filesystem-only run storage

- **Current issue**: Plans, generated files, reviews, and test plans are saved directly under the local `artifacts/` directory. There is no database, queryable run index, retention policy, or built-in backup/restore. Runs are tied to the machine and filesystem where the app is running.
- **Future task**: Introduce a persistence layer with a database for run metadata, task states, model settings, and artifact references. Evaluate SQLite for a single-user local deployment and PostgreSQL for concurrent or hosted use. Store larger file contents on a filesystem or object store and keep references/checksums in the database.
- **Acceptance ideas**: List and search runs from persisted metadata; reload a run after restarting the app; associate artifacts with a run and task; document schema migrations, backup, and retention; keep a filesystem-only mode available if practical.

### 2. Add run lifecycle and recovery

- **Current issue**: A run is sequential and synchronous. If a model call fails partway through, partial files may remain, but there is no clear task status, retry, resume, cancel, or cleanup interface.
- **Future task**: Persist run/task states such as queued, running, completed, and failed; record per-agent errors; allow retrying a failed task and resuming without regenerating completed tasks; provide cancellation and safe cleanup.

### 3. Add optional existing-repository context

- **Current issue**: Agents only receive the problem statement and files generated earlier in the current run. They cannot inspect an existing codebase, infer its framework, or reliably produce changes that fit an established project.
- **Future task**: Let a user provide a repository or selected files as read-only context. Start with explicit file selection and size limits; add ignore rules for secrets, binaries, generated directories, and dependency folders; keep repository modification disabled until a separately reviewed patch workflow exists.

### 4. Verify generated projects safely

- **Current issue**: Reviewer and testing agents produce suggestions, but their reports are not execution-based checks. Generated source and test files are not installed, linted, type-checked, or run.
- **Future task**: Add an opt-in isolated runner with resource, time, filesystem, and network limits. Require explicit user approval before executing generated projects, and show actual command output separately from model-generated review. Do not run projects inside the app container with its normal privileges.

### 5. Improve model/provider management

- **Current issue**: The Docker app connects to host Ollama through `host.docker.internal`; Ollama may need to listen beyond loopback. That API is unauthenticated by default. Provider selection and model-specific capability validation are basic.
- **Future task**: Support configurable container-to-host endpoints across Docker platforms, validate model availability from the app, provide clearer connection diagnostics, and document secure remote-provider configuration. Avoid exposing Ollama on untrusted networks.

### 6. Improve generation quality and artifact UX

- **Current issue**: Planner, coder, and synthesis responses can still be malformed or incomplete. Each structured response gets one bounded format-repair attempt; if synthesis still fails, a deterministic proposal merge is used with a warning. The UI is designed for local use and a small number of runs; it has no authentication, collaboration, or artifact retention controls.
- **Future task**: Improve bounded structured-output repair and quality checks, add consistency checks between acceptance criteria and tests, generated-file diff views, run search/filtering, configurable retention, and authentication/authorization before any multi-user deployment.

These items are starting points for future issues or pull requests. A contribution should define a narrow scope, security boundary, acceptance criteria, and tests before implementation.

## Security, Privacy, and Limitations

- With local Ollama, prompts and generated outputs are processed by the configured host model. A remote model provider receives prompts under that provider's terms. Do not submit secrets, personal data, or proprietary code unless that model host is approved to receive it.
- The planner, coding, reviewer, tester, and synthesis agents have no tools. The app does not inspect an existing repository, execute commands, run generated code/tests, or apply generated files to this repository.
- Generated paths are restricted to relative paths beneath the isolated project directory. Traversal, absolute paths, `.git`/`.env` paths, duplicate/case-colliding paths, and oversized plans/files are rejected.
- Prompt instructions and serialized JSON boundaries are defense-in-depth measures, not a guarantee against prompt injection. Model outputs can be unsafe, incorrect, incomplete, or misleading. Review generated code and agent reports before use.
- The reviewer and test planner provide model-generated analysis, not execution-based verification. Generated test files are not run automatically. Static syntax checks catch some formatting errors but do not guarantee that a project installs, starts, or behaves correctly.
- Agents do not receive an existing project checkout, so generated files may need adaptation to integrate with an existing application.
- The Docker app requires Ollama to be reachable from the host network. Docker Desktop does not reuse a host-only loopback listener automatically.

## License

This project is contributed under the repository's open-source license.
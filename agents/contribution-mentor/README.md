# Contribution Mentor

> A configurable AI agent that studies a code repository, matches developers to GitHub issues, and can prepare changes for explicit approval.

## Overview

### Problem Statement & Intended Users

New contributors often need help understanding an unfamiliar codebase and finding a realistic first contribution. Contribution Mentor uses a configurable language-model endpoint to analyze repository files, compare a developer's experience to open GitHub issues, and prepare a focused plan or reviewed patch.

### Key Features

- Reads source code, documentation, and common dependency manifests from a repository.
- Answers repository questions and suggests scoped contributions based on inspected files.
- Lists public open GitHub issues and matches them to a developer's experience.
- Creates an implementation and test plan for a selected issue.
- Can propose issue-specific file changes and applies them only after explicit confirmation.
- Uses configuration from `.env`; it does not hard-code a provider or model allowlist.
- Includes an OpenAI Chat Completions-compatible client wrapper. Ollama is one optional backend; compatible hosted and local providers can also be configured.
- Keeps normal runs read-only and excludes common credentials from repository context.

## Technical Stack

- **Language & Runtime:** Go 1.22+
- **Model API:** OpenAI Chat Completions-compatible HTTP API
- **Model provider:** Configurable OpenAI-compatible endpoint; Google Gemini is the default example, and Ollama remains available as an optional Docker backend
- **External APIs / Tools:** GitHub REST API; Go standard library

## Architecture & Data Flow

The agent uses a small layered, ports-and-adapters-inspired structure: the command is the composition root, `internal/mentor` contains the core agent workflows, `internal/config` handles environment configuration, and `internal/web` adapts the same agent for HTTP. The model provider and GitHub API are called through clients in the core package. This keeps transport/configuration separate without introducing a large framework or unnecessary interfaces.

```text
cmd/contribution-mentor/  CLI entry point and dependency wiring
internal/
  config/                 .env loading
  mentor/                 repository context, model client, GitHub issue workflows, approved patches
  web/                    localhost HTTP handlers and embedded browser UI
```

```text
[Repository files] ----+
                       +--> [Contribution Mentor] --> [Configured model API] --> [Answer/plan]
[GitHub open issues] --+                                      |
                                                              +--> [Reviewed changes]
                                                                   (explicit APPLY only)
```

The repository scanner selects supported text files, omits common generated directories and sensitive filenames, and limits context to 80 files and 72 KiB. GitHub issue descriptions are treated as untrusted input and truncated before being sent with the repository context to the configured model endpoint.

## Prerequisites

- Go 1.22+
- An OpenAI Chat Completions-compatible model endpoint and its credentials, if required

The example configuration uses Google's OpenAI-compatible Gemini API. Create a key in [Google AI Studio](https://aistudio.google.com/apikey) and add it to your local `.env`. Check Google's current free-tier limits and data terms before sending repository code. Ollama remains available as an optional Docker-backed provider.

## Installation & Setup

Run these commands from this directory:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

The example selects Gemini. Add your API key to the local `.env` file; never place it in `.env.example` or commit it. To use Ollama instead, change the provider, URL, and model to your local/Docker Ollama settings. Start the local web UI with:

```powershell
go run ./cmd/contribution-mentor -web
```

Open `http://127.0.0.1:8080`. The `make run` target is the Docker Compose workflow and is not required for local web testing.

## Configuration

All provider/model settings are read from `.env`:

| Variable | Required | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | Yes | `openai-compatible` for Gemini or another compatible endpoint, or `ollama` to use Ollama through Docker |
| `LLM_BASE_URL` | Yes | API base URL; the Gemini example uses `https://generativelanguage.googleapis.com/v1beta/openai` |
| `LLM_MODEL` | Yes | Exact model identifier expected by the selected endpoint; the Gemini example uses `gemini-3.8-flash` |
| `LLM_API_KEY` | Provider-dependent | API key; leave empty if the endpoint does not require one |
| `OLLAMA_IMAGE` | When using Ollama | Ollama Docker image to run |
| `OLLAMA_SERVER_HOST` | When using Ollama | Internal Ollama host used by the model-download container |
| `GITHUB_TOKEN` | No | Optional GitHub token for increased rate limits or private repositories |
| `GITHUB_REPO` | No | GitHub repository in `owner/name` form |
| `EXPERIENCE` | For GitHub mode | Developer languages, experience level, and interests |
| `ISSUE` | No | Open issue number for a focused plan or implementation |
| `IMPLEMENT` | No | Set `true` to propose changes for a selected issue; still requires typing `APPLY` |
| `PROJECT_DIR` | Yes | Local repository checkout to inspect; defaults are documented in `.env.example` |
| `QUESTION` | No | Question for repository Q&A |

The `.env` file is ignored by Git. Never commit provider keys or a populated local `.env`.

## How to Run

The Go program loads `.env` directly when run from this directory; variables already present in the process environment take precedence.

For host-only development, point `LLM_BASE_URL` at a model API reachable from the host, such as a host-installed Ollama at `http://localhost:11434/v1`, then run:

```powershell
go run ./cmd/contribution-mentor -question "What does this repository do?"
```

This command does not start Docker. `make run` is the deployment-style Docker workflow described below.

### Use the local web interface

Configure `LLM_BASE_URL` in `.env` to an endpoint reachable from the host, then start the UI from this directory:

```powershell
go run ./cmd/contribution-mentor -web
```

Open `http://127.0.0.1:8080`, enter the local repository path, and ask the mentor to analyze it. Separate buttons run `go test ./...` or `go vet ./...` from that repository root. Each check requires a root-level `go.mod` and runs only after you click its button. Tests and vet execute repository code on your computer; only run them on code you trust. The server binds to loopback and rejects cross-origin requests. Use `go run ./cmd/contribution-mentor -web -port 8090` to select another port.

Repository source selected by the scanner is sent to the configured model provider when you ask a question. Check that provider's data-handling terms before analyzing private code. The CLI remains available for the existing workflows:

```powershell
go run ./cmd/contribution-mentor -repo E:\path\to\repo -question "What does this project do?"
```

### Ask about a repository

Set `QUESTION` in `.env`, then:

```powershell
make run
```

## Example Input & Output

### Repository question

Input:

```text
What does this application do? Summarize its API, storage, and payment flow.
```

Example response (illustrative; wording and details vary by provider and model):

```text
- Dodo Payments is a Go invoice and payment API.
- It uses PostgreSQL for application data and a mock PSP to simulate payment outcomes.
- Payment requests use idempotency keys; the service also supports recovery and signed webhooks.
- Start the API and its dependencies with `docker compose up --build`.
```

To ask about the local `dodoPayments` checkout:

```powershell
go run ./cmd/contribution-mentor `
  -repo E:\go\src\dodoPayments `
  -question "What does this application do? Summarize its API, storage, and payment flow."
```

### Find issues matching your experience

To discover issues, provide your local checkout path with `-repo`, the GitHub repository in `OWNER/REPO` form with `-github`, and a short description of your experience with `-experience`:

```powershell
go run ./cmd/contribution-mentor `
  -repo E:\go\src\dodoPayments `
  -github OWNER/REPO `
  -experience "Go developer, familiar with REST APIs and PostgreSQL"
```

Replace `OWNER/REPO` with the repository's GitHub owner and name. The agent fetches up to 20 recently updated open issues (excluding pull requests), prints their issue numbers and links, then asks the configured model to rank suitable options for your experience. Review the issue on GitHub and choose one of the suggested issue numbers; the model's recommendation is a shortlist, not a guarantee that an issue is still available.

### Get a plan for one issue

Pass the chosen issue number using `-issue` to get a focused explanation and implementation/test plan:

```powershell
go run ./cmd/contribution-mentor `
  -repo E:\go\src\dodoPayments `
  -github OWNER/REPO `
  -issue 42 `
  -experience "Go developer, familiar with REST APIs and PostgreSQL"
```

Here `42` is an example issue number; use a number returned by the discovery command or shown in the GitHub issue URL.

### Propose and apply changes after review

Set `IMPLEMENT=true` as well as `GITHUB_REPO`, `ISSUE`, and `EXPERIENCE` in `.env`, then run `make run`. The agent displays the proposed changes and writes nothing unless you type `APPLY`. The proposal is limited to five files and 48 KiB of generated content. Review the result and run the target repository's tests yourself.

For Ollama, the Make target starts the configured Ollama Docker image and pulls the exact `LLM_MODEL` value. For `openai-compatible`, it does not start Ollama. `make down` stops the Docker Compose services while preserving Ollama's model cache.

To switch models, edit only `LLM_MODEL` in `.env`. For example:

```dotenv
LLM_MODEL=gemma4:e4b
```

## Example Configuration

The committed `.env.example` uses Google's OpenAI-compatible Gemini endpoint and leaves `LLM_API_KEY` empty. Add a key only to your ignored local `.env`, or configure another compatible endpoint. The application sends a standard non-streaming `/chat/completions` request using the configured model ID; it does not validate against a hard-coded model list.

## How to Test

```powershell
go test ./...
go vet ./...
go build ./...
docker compose config --quiet
docker build -t contribution-mentor:local .
```

Tests use mock HTTP servers and do not require a model or GitHub token.

GitHub Actions checks formatting, tests, vet, build, Compose configuration, the Docker image build, documentation and environment-template completeness, secret hygiene, and pull-request scope. CI does not call a live model API or validate provider credentials; those depend on the configured provider and local key.

## Known Limitations

- The model endpoint must support the OpenAI Chat Completions request/response format. Providers with a different API format require an adapter.
- GitHub API access requires internet and may be rate-limited without a token.
- Repository context is bounded and does not follow `.gitignore` rules beyond built-in exclusions.
- Model output quality depends on the configured model and its context limit.
- Hosted model APIs may return rate-limit or temporary availability errors.
- Proposed changes are AI-generated; inspect them and run tests before using them.

## Security & Privacy Considerations

- Provider URL, model, and credentials are configuration, not compiled into the program. The API key is sent only as a bearer token to the configured model endpoint.
- Selected source and issue text are sent to the configured model provider. Review the endpoint and its data-handling terms before sending private code.
- By default, Docker mounts the repository read-only and runs the agent as a non-root user. Explicit `IMPLEMENT=true` makes the mount writable and runs the agent as root so changes can be saved to the host checkout.
- Issue content and repository files are treated as untrusted model input.
- Proposed paths are restricted to the repository; sensitive/generated paths, symlinks, oversized proposals, and files changed since inspection are rejected.
- The CLI does not execute repository code. The local web UI can execute only the fixed `go test ./...` and `go vet ./...` checks after an explicit click.

## Future Improvements

- [ ] Add GitHub issue discovery and planning to the web interface.
- [ ] Add support for repository-specific test commands after explicit user approval.

## License

This project is contributed under the repository's MIT license.

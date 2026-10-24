# Cloud Lifecycle Remediation Agent

> Autonomous Go agent (Google ADK) that patches Terraform for AWS EKS/RDS version deprecations and EC2/RDS/EKS instance-type retirements, validates HCL, and opens draft remediation pull requests.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Teams miss AWS EKS and RDS end-of-support deadlines because version bumps span clusters, add-ons, and parameter groups across Terraform repos.
- **Intended Users**: Platform engineers, SREs, and cloud foundation teams managing Terraform-based AWS infrastructure.

### Key Features
- Ingests structured deprecation events (service, resource, current/target values, deadline, repo path).
- Supports **EKS**, **RDS** engine versions, **RDS_INSTANCE** classes, **EC2** instance types, and **EKS_NODEGROUP** instance types.
- Scans Terraform for target resources and related components (EKS add-ons, RDS parameter groups).
- Applies targeted HCL patches with compatibility guidance from a curated lookup table.
- Runs `terraform fmt` and `terraform validate` after patching.
- Creates an isolated bot branch and draft GitHub PR (or simulates locally with `SIMULATE_PR=true`).
- Enforces guardrails: never targets `main`/`master` for writes or merges.

---

## Technical Stack

- **Language & Runtime**: Go 1.26+ (required by `google.golang.org/adk/v2` v2.6)
- **Agent Framework**: [google/adk-go](https://github.com/google/adk-go) (`google.golang.org/adk/v2`)
- **Models**: Gemini 2.5 Flash (default, configurable via `MODEL_NAME`)
- **External Tools**: Terraform CLI, Git, GitHub CLI (`gh`) for real PR flow

---

## Architecture & Data Flow

```
[Deprecation Event JSON]
        |
        v
[LLM Agent + System Protocol]
        |
        +--> ScanTerraformConfigs
        +--> FetchVersionUpgradeGuidance
        +--> PatchTerraformFile
        +--> RunTerraformValidate (retry loop on failure)
        +--> CreateRemediationPR (bot branch only)
        |
        v
[Summary: changes, validation, PR URL]
```

---

## Prerequisites

- Go 1.26 or newer
- Terraform 1.5+ on `PATH` for validation (macOS: `brew tap hashicorp/tap && brew install hashicorp/tap/terraform`)
- **OpenAI** (`OPENAI_API_KEY`) or **Gemini** (`GOOGLE_API_KEY` / `GEMINI_API_KEY`)
- Optional for real PRs: `git`, `gh`, and a configured Git remote

---

## Installation & Setup

```bash
cd agents/cloud-lifecycle-remediation
cp .env.example .env
# Edit .env with your API key

go mod download
```

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | No | auto | `openai` or `gemini` (auto picks OpenAI if `OPENAI_API_KEY` is set) |
| `OPENAI_API_KEY` | Yes* | — | OpenAI Platform API key |
| `GOOGLE_API_KEY` | Yes* | — | Gemini API key when using `LLM_PROVIDER=gemini` |
| `GEMINI_API_KEY` | Yes* | — | Alias for Gemini |
| `MODEL_NAME` | No | provider default | e.g. `gpt-4o-mini` or `gemini-2.5-flash` |
| `SIMULATE_PR` | No | unset | Set `true` to skip `git push` / `gh pr create` |

\*Set credentials for the provider you use (`OPENAI_API_KEY` or Gemini keys).

---

## How to Run

Sample Terraform lives under [`test-infra/`](./test-infra/) (EKS + RDS examples). See [`test-infra/README.md`](./test-infra/README.md) for all demo events.

Default demo event (EKS `production-core` 1.28 → 1.30 in `./test-infra`):

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_key
export SIMULATE_PR=true
go run .
```

Custom event JSON:

```bash
go run . '{"service":"EKS","resource_name":"production-core","current_version":"1.28","target_version":"1.30","eos_deadline":"2026-11-30","repo_dir":"./test-infra"}'
```

---

## Example Input & Output

### Example Input

```json
{
  "service": "EKS",
  "resource_name": "production-core",
  "current_version": "1.28",
  "target_version": "1.30",
  "eos_deadline": "2026-11-30",
  "repo_dir": "./test-infra"
}
```

### Example Output (abridged)

The agent summarizes patched attributes (`version`, `addon_version`), `terraform validate` status, migration checklist items from guidance, and a draft PR URL (simulated when `SIMULATE_PR=true`).

---

## How to Test

```bash
go test ./...
terraform -chdir=test-infra validate   # after agent run / manual patch
```

---

## Known Limitations

- Upgrade guidance is mock/curated—not a live AWS API feed.
- HCL patching uses block-aware regex, not a full HCL parser (sufficient for demo-style resources).
- Real PR creation requires GitHub credentials and a remote; use `SIMULATE_PR=true` for offline demos.

---

## Security & Privacy Considerations

- API keys load from environment only; never commit `.env`.
- The agent runs `terraform`, `git`, and `gh` locally with the invoking user's permissions.
- It refuses protected branch names and only commits on explicitly named bot branches.

---

## License

This project is contributed under the repository's open-source license.

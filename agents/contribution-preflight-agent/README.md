# Contribution Preflight Agent

> A hub-and-spoke Google ADK agent that checks any project folder against configurable contribution rules, reviews its README with a local Gemma model, and adds a lightweight ASPM-style posture check with a CycloneDX SBOM, all in one PDF/CSV report, entirely inside Docker with no API key.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Contributions to community repos are often delayed or closed for the same avoidable reasons: wrong folder naming, missing files, leftover template text, committed secrets, and weak READMEs. Contributors find out only after a maintainer reviews the PR.
- **Intended Users**: Contributors who want a self-check before opening a PR, and maintainers who want a quick first-pass review.

### Key Features
- **Works on any repo**: the structure rules are not hard-coded. Pick a built-in profile (`generic` by default, or `gdgcblr`) or drop a `.preflight.json` into the project folder. See "Rules".
- **Structure check**: directory naming, required files, a dependency manifest and leftover template placeholders in the README, all driven by the active rules.
- **Security check**: flags `.env`, key and credential files, and common secret patterns (Google, OpenAI-style, GitHub, AWS keys, private key blocks) in text files.
- **Docs review**: a local Gemma model reads the README and the file list and returns up to five concrete fixes.
- **ASPM and SBOM**: a posture spoke builds a CycloneDX 1.5 SBOM from the project's dependency manifests and flags unpinned dependencies and risky Dockerfile settings. An optional `--vuln-scan` looks up known vulnerabilities on OSV.dev. See "ASPM and SBOM".
- **Hub-and-spoke design**: one master agent controls every sub-agent. See below.
- **Offline mode**: `--no-llm` skips the model and runs only the deterministic checks. `--no-aspm` skips the posture check and SBOM.
- **One combined report**: each run saves a timestamped PDF and CSV to the `reports/` folder next to `docker-compose.yml`, with Part 1 (PR Preflight) and Part 2 (ASPM and SBOM) in the same file, plus the SBOM as a separate CycloneDX JSON file. The terminal shows one summary line only.
- **Exit code**: `0` when the structure and security checks pass and the ASPM check has no HIGH finding, `1` otherwise.

---

## Technical Stack

- **Language & Runtime**: Python 3.12 inside Docker
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk` 2.13.0), LiteLLM (`litellm` 1.106.2)
- **Models**: Gemma 3 4B (`gemma3:4b`) served by Ollama in a container
- **External APIs / Tools**: none by default. No API keys and no network calls after the model is downloaded. The only optional network feature is `--vuln-scan`, which queries OSV.dev.

---

## Architecture & Data Flow

```
                  +----------------------+
 project folder ->|   preflight_master   |-> report + exit code
                  |  (controls all work) |
                  +----------+-----------+
                             |
       +---------------+-----+---------+----------------+
       |               |               |                |
 structure_spoke  security_spoke  posture_spoke      docs_spoke
 (plain code)     (plain code)    (plain code:       (Gemma via Ollama)
                                  SBOM + posture)
```

- `preflight_master` is the only agent that reads input, decides the order, collects results and writes the final report.
- The spokes never call each other and never talk to the user. Each one returns its result to the master.
- `posture_spoke` runs unless `--no-aspm` is set. `docs_spoke` runs unless `--no-llm` is set.
- Gemma `gemma3:4b` reports no tool-calling capability in Ollama, so the master runs the spokes in a fixed order in code instead of letting the model choose tools. Gemma is used only for the README review.

---

## Prerequisites

- **Docker Desktop** (macOS or Windows) or Docker Engine with Docker Compose v2.24 or newer
- **Git**
- **About 8 GB of RAM available to Docker** (Docker Desktop: Settings, Resources). The author ran it successfully with 7.4 GiB allocated; lower amounts were not tested.
- **About 13 GB of free disk** for the images and the model (measured: Ollama image 8.4 GB, agent image 0.7 GB, `gemma3:4b` model 3.4 GB)
- Internet access on the first run, to pull images and download the model (about 3.4 GB). Later runs skip the model download when the model is already in the Docker volume (a run with no internet at all was not tested). `--vuln-scan` always needs internet.

---

## Installation & Setup

### One-line install and run

Reviews the project folder you run it from. Replace `.` with a path to review another project.

**macOS / Linux (bash or zsh):**
```bash
git clone https://github.com/gdgcblr/open-source-agents.git && cd open-source-agents/agents/contribution-preflight-agent && TARGET_PROJECT=. docker compose run --rm agent
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/gdgcblr/open-source-agents.git; cd open-source-agents\agents\contribution-preflight-agent; $env:TARGET_PROJECT="."; docker compose run --rm agent
```

The first run downloads the model and takes several minutes depending on your connection. Later runs reuse it from a Docker volume.

### Step by step

1. Clone and enter the project:
   ```bash
   git clone https://github.com/gdgcblr/open-source-agents.git
   cd open-source-agents/agents/contribution-preflight-agent
   ```
2. Optional: copy the example environment file and edit it.
   ```bash
   # macOS / Linux
   cp .env.example .env
   ```
   ```powershell
   # Windows (PowerShell)
   Copy-Item .env.example .env
   ```
3. Run the agent against a project folder:
   ```bash
   # macOS / Linux
   TARGET_PROJECT=../../agents/some-project docker compose run --rm agent
   ```
   ```powershell
   # Windows (PowerShell)
   $env:TARGET_PROJECT="..\some-project"; docker compose run --rm agent
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `TARGET_PROJECT` | No | `.` | Path of the project folder to review. Mounted read-only at `/project`. |
| `MODEL_NAME` | No | `gemma3:4b` | Ollama model used for the README review. It is pulled automatically. |
| `PROJECT_NAME` | No | *(empty)* | Name used in report filenames. If empty, the title of the project's `README.md` is used, else `project`. |
| `REPORTS_DIR` | No | `./reports` | Host folder where reports are saved (relative to `docker-compose.yml`). |
| `PREFLIGHT_VULN_SCAN` | No | *(empty)* | Set to `1`, `true`, `yes` or `on` to enable the OSV.dev vulnerability lookup (same as `--vuln-scan`). Off by default because it sends package names and versions over the network. |
| `PREFLIGHT_PROFILE` | No | *(empty)* | Built-in rules profile: `generic` or `gdgcblr`. Empty means use `.preflight.json` in the project if present, otherwise `generic`. The `--profile` flag does the same. |

No secrets are required. Never commit a real `.env` file.

---

## How to Run

```bash
TARGET_PROJECT=<path-to-project> docker compose run --rm agent
```

Offline, deterministic checks only (no model, no Ollama):
```bash
TARGET_PROJECT=<path-to-project> docker compose run --rm --no-deps agent /project --no-llm
```

Skip the posture check and SBOM, or add the opt-in vulnerability lookup:
```bash
TARGET_PROJECT=<path-to-project> docker compose run --rm agent /project --no-aspm
TARGET_PROJECT=<path-to-project> docker compose run --rm agent /project --vuln-scan
```

On Windows PowerShell, set the variable first with `$env:TARGET_PROJECT="<path>";` and run the same `docker compose` command.

---

## Rules

The structure check is driven by a set of rules. Which rules apply is decided in this order:

1. `--profile <name>` (or `PREFLIGHT_PROFILE`) uses that built-in profile and ignores `.preflight.json`.
2. Otherwise, a `.preflight.json` in the project folder is layered on top of the `generic` profile.
3. Otherwise, the `generic` profile applies.

| Profile | What it checks |
| :--- | :--- |
| `generic` | `README.md` exists and has no leftover template placeholders. Any directory name is accepted. |
| `gdgcblr` | The rules of `gdgcblr/open-source-agents`: lowercase kebab-case name, non-generic name, `README.md`, `.gitignore` and `.env.example`, a dependency manifest, and no template placeholders. |

The secret and credential scan is the same for every profile.

Example `.preflight.json` (every key is optional; unknown keys and wrong types are reported as errors):

```json
{
  "kebab_case": true,
  "forbidden_names": ["demo", "test"],
  "required_files": ["README.md", "LICENSE", "Dockerfile"],
  "manifest_any_of": ["package.json", "pyproject.toml"],
  "template_markers": ["TODO: fill in"]
}
```

Run with a specific profile:
```bash
TARGET_PROJECT=<path-to-project> docker compose run --rm agent /project --profile gdgcblr
```

---

## ASPM and SBOM

`posture_spoke` adds a lightweight, ASPM-style (application security posture) check for the project folder, plus a software bill of materials. It runs by default and can be turned off with `--no-aspm`.

**SBOM.** Dependencies are read from the manifests in the project root: `requirements.txt`, `pyproject.toml`, `package.json` and `go.mod`. They are written as a CycloneDX 1.5 JSON file saved next to the PDF and CSV. Dependencies without an exact version are listed with their version spec instead.

**Posture findings.** Each finding has a severity:

| Check | Severity |
| :--- | :--- |
| Dependency not pinned to an exact version | WARN |
| `package.json` without a lockfile (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`) | WARN |
| Dockerfile base image with no tag or `:latest` | WARN |
| Dockerfile with no non-root `USER` | WARN |
| Dockerfile `curl ... \| sh` style install | WARN |
| Secret-like `ENV` or `ARG` (name contains KEY, TOKEN, SECRET or PASSWORD) set to a value in a Dockerfile | HIGH |
| Known vulnerability for a pinned dependency (only with `--vuln-scan`) | HIGH |

HIGH findings fail the verdict and set the exit code to `1`. WARN findings are reported but do not fail the run.

**Vulnerability lookup (opt-in).** `--vuln-scan` (or `PREFLIGHT_VULN_SCAN=1`) sends the names and versions of pinned PyPI, npm and Go dependencies to the public OSV.dev API and reports any known vulnerability IDs. It is off by default because it is the only feature that uses the network. If the lookup fails, the run continues and reports a WARN.

```bash
TARGET_PROJECT=<path-to-project> docker compose run --rm agent /project --vuln-scan
```

**What this is not.** It is a posture check for one project folder, not a full ASPM platform that aggregates findings from many scanners. It reads only root-level manifests, lists direct dependencies only (no transitive resolution), and has no Cargo support. Severity for vulnerabilities is not evaluated: any known vulnerability is treated as HIGH.

This project's own `Dockerfile` is reported as WARN for running as root, because it needs to write to the bind-mounted `reports/` folder.

---

## Reports

Each run writes up to three files to the `reports/` folder, named `preflight_<project>_<rules>_<YYYYMMDD-HHMMSS>` plus an extension. The timestamp is UTC.

- **PDF** (`.pdf`): one readable report. Part 1 is PR Preflight (structure, security, Gemma suggestions). Part 2 is ASPM and SBOM (posture findings, component list, vulnerability scan status).
- **CSV** (`.csv`): one row per finding with the columns `generated_utc, project, rules, section, check, status, detail`. The `section` column is `pr_preflight`, `aspm` or `summary`. It is ready for a spreadsheet or a script.
- **SBOM** (`_sbom.cdx.json`): the CycloneDX 1.5 file. It is not written when `--no-aspm` is set.

Choose the PDF/CSV format with `--format pdf`, `--format csv` or `--format both` (default). `reports/` is ignored by Git.

The terminal only shows a summary line, for example:
```
Verdict: PASS. Saved: preflight_contribution-preflight-agent_gdgcblr_20261024-081110.csv, preflight_contribution-preflight-agent_gdgcblr_20261024-081110.pdf, preflight_contribution-preflight-agent_gdgcblr_20261024-081110_sbom.cdx.json
```

---

## Example Input & Output

### Example Input
```bash
TARGET_PROJECT=<path-to-demo-project> docker compose run --rm agent /project --no-llm --vuln-scan
```
Run against a small demo project with a `README.md` and a `requirements.txt` that pins two deliberately old packages. `--no-llm` skips the Gemma review so the example is quick; without it, the report also has a Docs review section.

### Example Output
The run below is the CSV for a small demo project that contains `requests==2.19.1` and `pyyaml==5.3` (deliberately old versions), run with `--no-llm` and `--vuln-scan`. It exits with code 1 because of the HIGH findings. The OSV ids come from the live OSV.dev database at the time of the run.

```
generated_utc,project,rules,section,check,status,detail
2026-10-24T08:13:08Z,vuln-demo,generic,pr_preflight,structure,PASS,No issues found.
2026-10-24T08:13:08Z,vuln-demo,generic,pr_preflight,security,PASS,No issues found.
2026-10-24T08:13:08Z,vuln-demo,generic,aspm,sbom,INFO,2 components (2 PyPI); file: preflight_vuln-demo_generic_20261024-081308_sbom.cdx.json
2026-10-24T08:13:08Z,vuln-demo,generic,aspm,posture,HIGH,Known vulnerability GHSA-9hjg-9r4m-mvj7 in requests 2.19.1.
2026-10-24T08:13:08Z,vuln-demo,generic,aspm,posture,HIGH,Known vulnerability GHSA-9wx4-h78v-vm56 in requests 2.19.1.
... 12 more HIGH rows, one per known vulnerability ...
2026-10-24T08:13:08Z,vuln-demo,generic,aspm,vulnerability_scan,INFO,done: 14 known vulnerabilities found (OSV.dev)
2026-10-24T08:13:08Z,vuln-demo,generic,summary,verdict,FAIL,"Decided by structure, security and high-severity ASPM findings."
```

On the author's machine (Windows 11, Docker Desktop with 7.4 GiB allocated, 16 CPUs, model already downloaded) full runs with the Gemma review took between about 1 and 2.5 minutes. Runs with `--no-llm` finish in seconds.

---

## How to Test

```bash
docker compose run --rm --no-deps --entrypoint python agent -m pytest -q /app/tests
```

This runs 73 unit tests for the structure, security, rules-loading, SBOM, posture and report-writing logic. No model or network is needed.

### Smoke test

```bash
docker compose run --rm --no-deps --entrypoint python agent -m pytest -q /app/tests/test_smoke.py -v
```

The smoke test runs the real command-line tool end to end against a generated good project and a generated bad project, then checks the exit codes and the saved PDF, CSV and SBOM files. It needs no model and no network, so it is a quick way to confirm an install works.

---

## Known Limitations

- Tested on Windows 11 with Docker Desktop only. macOS and Linux commands follow the same Docker Compose flow but were not run by the author.
- `gemma3:4b` is small. Its README review can be generic or occasionally wrong, so treat it as suggestions, not a verdict. The pass/fail result and exit code come only from the deterministic checks.
- The README review reads at most the first 12,000 characters of the README and the first 100 file names.
- Only two built-in profiles exist. Other repos need a `.preflight.json`. The rules cover file names, naming and README placeholders only; they cannot yet express checks such as "the PR touches only one folder".
- Secret scanning is pattern-based and can miss unusual secrets or flag harmless strings. It skips files larger than 1 MB and common dependency folders.
- Reports use a Latin-1 PDF font, so characters outside it (for example non-Latin scripts) appear as `?`. Common punctuation such as curly quotes and dashes is converted.
- Gemma suggestions are split into report rows by their bullet markers. If the model does not answer in bullets, or wraps a bullet onto extra lines, the PDF and CSV may hold only the first line of each suggestion.
- Report timestamps are in UTC because the container has no local timezone.
- The ASPM check reads only root-level manifests and direct dependencies. There is no transitive dependency resolution and no Cargo support. Dependencies listed in subfolders are not found.
- Pinning is judged from the manifest. A `package.json` range is reported as unpinned even if a lockfile fixes the version.
- `--vuln-scan` checks only pinned PyPI, npm and Go dependencies, needs internet access, and treats every known vulnerability as HIGH because severity is not evaluated. A failed lookup is reported as a WARN and skipped.
- Dockerfile checks are line-based and only look at `Dockerfile`, `Dockerfile.*` and `*.dockerfile` in the project root.
- Running Gemma on CPU is slow on low-end machines. If the model runs out of memory, give Docker more RAM or set `MODEL_NAME` to a smaller model.

---

## Security & Privacy Considerations

- **Secrets Handling**: No credentials are needed. `.env` is excluded from the image by `.dockerignore` and ignored by Git.
- **Data Privacy**: The README text is sent only to the Ollama container on your own machine. Nothing leaves it. The one exception is the opt-in `--vuln-scan`, the only feature that uses the network: it sends dependency names and versions (not your code) to OSV.dev.
- **Safety**: The agent never executes code from the reviewed project. The project folder is mounted read-only.

---

## Future Improvements

- [ ] Check that a PR diff touches only the project folder.
- [ ] Add more built-in profiles for popular contribution guides.
- [ ] Verify the macOS and Linux commands on real machines.
- [ ] Resolve transitive dependencies from lockfiles for a fuller SBOM.
- [ ] Add Cargo support.
- [ ] Use severity data from OSV instead of treating every vulnerability as HIGH.

---

## License

*This project is contributed under the repository's open-source license.*

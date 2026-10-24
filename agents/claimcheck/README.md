# ClaimCheck

> Find the gap between what a project says and what its commands, API and image actually do.

## Overview

### Problem Statement & Intended Users

READMEs drift, APIs stop matching their contracts, and deployed images become
stale. ClaimCheck helps maintainers and reviewers turn supported project claims
into repeatable checks, rather than asking a language model whether docs "look right."

### Key Features

- Execute simple fenced README commands in disposable, network-disabled Docker
  containers; check exit codes and optional documented output.
- Find broken relative README links.
- Probe an explicitly selected live API against OpenAPI response status, media
  type and JSON schema, including local schema references.
- Compare final Dockerfile configuration with an already built image's immutable ID
  and configuration: `USER`, `WORKDIR`, exec-form `CMD`/`ENTRYPOINT`, `ENV`, `EXPOSE`.
- Use a **Google ADK agent with native Ollama tool calling**, or run the same checks
  deterministically without a model. **No LiteLLM.**
- Keep tool-collected evidence separate from model commentary. Unknown, blocked,
  failed-to-run and unexecuted checks never become passes.
- Demonstrate **eight deliberate lies and five truthful controls** in one fixture.

## Technical Stack

- Python 3.11+ (development and demos tested with Python 3.12).
- Google ADK 2.x; a small `BaseLlm` adapter calls Ollama `/api/chat` directly.
- `httpx`, PyYAML safe loading, JSON Schema validation, standard-library CLI.
- `uv` with a committed lockfile; optional `mise` pins Python, uv, Node and OpenSpec.
- Docker for isolated README execution and image inspection; no Docker socket in
  the check containers.
- OpenSpec 1.4.1 for proposal/spec/design/task artifacts.

## Architecture & Data Flow

```text
README.md + Dockerfile + openapi.yaml/yml/json
                     |
              bounded discovery
                     |
               stable claim IDs
                     |
      +--------------+------------------+
      |                                 |
deterministic audit            ADK + native Ollama
      |                       list_claims / verify_all_claims
      +--------------+------------------+
                     |
           policy-enforced check tools
      +--------------+------------------+
      |              |                  |
Docker command   live API probes   image inspection
  snapshot        (no redirects)     (no execution)
      +--------------+------------------+
                     |
           authoritative evidence ledger
                     |
         report.json + report.md
         (model commentary is advisory)
```

The model cannot change a verdict, add arbitrary commands, select a new network
target or access arbitrary files. It selects tools over pre-discovered IDs.
CLI approvals, not model reasoning, control capabilities.

## Prerequisites

- macOS or Linux, `make`, and `uv`. Windows is not supported by the POSIX process
  timeout/cleanup implementation; use a Linux environment.
- Docker daemon for the full demo and command execution.
- Ollama with a tool-capable model only for `--agent`.
- OpenSpec CLI only for spec workflow/validation. Node >=20.19 is needed by its CLI.
- No API keys or paid services are required.

## Installation & Setup

```sh
cd agents/claimcheck
make setup
make help
```

`make setup` uses the lockfile and creates `.env` from `.env.example` only when
it does not already exist. It never silently installs Docker, mise, or OpenSpec.

With mise installed, use the pinned toolchain:

```sh
mise trust                 # review mise.toml before trusting it
mise install
mise exec -- make setup
mise run check
```

Without mise, install uv and OpenSpec with your platform's package manager and
run `make` directly. `make docker-prepare` explicitly pulls the pinned Python
sandbox image; it is not downloaded implicitly by an audit.

### Development container

Open **this ClaimCheck folder** locally in VS Code and choose **Reopen in
Container**. The supplied [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json)
bind-mounts the host folder at `/workspaces/claimcheck`. Source stays on the host.
Keep project clones inside the mounted workspace rather than an ephemeral home directory.

The development container deliberately has no Docker socket mount. Run the
Docker-dependent demo on the host, or use a separately administered Docker
environment. `make demo-lite` works inside the container without Docker.
Push working commits: a bind mount or volume is not a backup.

## Configuration & Environment Variables

Edit `.env` in this directory. The CLI reads **only the current working
directory's `.env`**, not a target project's environment file.

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_API_BASE` | `http://localhost:11434` | Native Ollama server, not an OpenAI-compatible `/v1` URL |
| `OLLAMA_MODEL` | `hf.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL` | Requested tool-capable model |
| `CLAIMCHECK_ALLOW_REMOTE_MODEL` | `0` | Set to `1` to allow sending claims/evidence off-machine |
| `CLAIMCHECK_ALLOW_HTTP_MODEL` | `0` | Additional explicit consent for remote plaintext HTTP |

For a remote Ollama server reachable only over HTTP, your local ignored `.env`
can contain:

```dotenv
OLLAMA_API_BASE=http://<ollama-host>:11434
OLLAMA_MODEL=hf.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL
CLAIMCHECK_ALLOW_REMOTE_MODEL=1
CLAIMCHECK_ALLOW_HTTP_MODEL=1
```

Plain HTTP exposes request/response data in transit. Prefer an HTTPS endpoint or
an SSH tunnel to localhost. Do not audit private projects through an untrusted
server. Only synthetic fixture data was used for the live integration check.

## How to Run

### Reproducible demonstrations

```sh
make docker-prepare
make doctor
make demo                  # all checks, no LLM or hosted-model cost
make doctor-model          # also confirm configured model exists
make demo-agent            # same evidence, orchestrated by real ADK + Ollama
make demo-lite             # no Docker/model; unsupported checks stay unverified
```

The full demo builds a deliberately stale image from `Dockerfile.image` and
compares it to the **different** declared `Dockerfile`. It launches a bundled
Notes API on an ephemeral loopback port, then stops it and removes the temporary
image/containers. It does not execute a server taken from an audited project.

Reports go to ignored `reports/demo/`, `reports/demo-agent/` and
`reports/demo-lite/`. `report.json` includes source lines, claim IDs, observed
results, captured command output, image IDs and schema-error locations. Model
runs additionally record tool names and token counts.

### Audit another project

```sh
# Inspection/probes only; README commands stay not_verified.
uv run --locked claimcheck audit /absolute/path/to/project \
  --base-url http://127.0.0.1:8000 --image my-app:local

# Explicitly permit execution of that project's simple documented commands.
uv run --locked claimcheck audit /absolute/path/to/project \
  --base-url http://127.0.0.1:8000 --image my-app:local --allow-exec \
  --output reports/my-app

# Add --agent only after reviewing which data will be sent to your model.
```

You must start the target API and build/select its image yourself. ClaimCheck
does not trust `servers` URLs in a spec and never auto-builds an audited
Dockerfile. Remote API targets additionally require `--allow-remote-api`;
remote plaintext HTTP requires `--allow-http-api` too. Redirects are not followed.

Audit exit codes: **0** all discovered checks pass; **1** observed drift;
**2** an operational/configuration error; **3** no failures/errors but incomplete
verification. A demo returns 0 only when its planted failures are detected as
expected; it does not hide audit failures.

### README command syntax

Simple one-line commands inside `sh`, `bash`, `shell` or `console` fences are
checked. A following comment can assert an output substring:

````markdown
```sh
python app.py --self-test
# expect: notes demo ready
```
````

Without `# expect:`, success means only exit code 0. Commands run independently:
no shell, state carried between blocks, substitutions, pipes, redirection,
package installation over the network or automatic interpreter guessing.
Unsupported shell syntax stays `not_verified`, not failed.

## Example Input & Output

The [lying-notes fixture](fixtures/lying-notes) deliberately has:

| Surface | Planted lie | Evidence |
|---|---|---|
| README | `python bootstrap.py` works | File absent; Python exits 2 |
| README | self-test prints production connectivity | Actual stdout is `notes demo ready` |
| README | deployment guide exists | Missing local link target |
| Dockerfile | production environment | Stale image records `APP_MODE=demo` |
| Dockerfile | port 8000 | Stale image records `9000/tcp` |
| Dockerfile | short startup CMD | Stale image CMD has extra port arguments |
| OpenAPI | note IDs are integers | Live `/notes` returns a string ID |
| OpenAPI | `/export` works | Live server returns 404 |

Real full-demo output:

```text
{
  "passed": 5,
  "failed": 8,
  "not_verified": 0,
  "error": 0
}
Demo verified: 8 planted lies detected.
```

The positive controls are the self-test command, existing source link, image
user/working-directory settings and `/health`. The lite demo reports 2 passed,
3 failed and 8 not verified; it never fabricates Docker or execution evidence.

## How to Test

```sh
make check                 # lint, strict types, tests, OpenSpec validation
make test                  # includes mocked native Ollama + real ADK tool loop
make demo                  # real Docker and live local HTTP fixture
make demo-agent            # optional live model integration; not part of offline tests
make build                 # wheel + sdist with bundled fixture
```

Tests do not contact the remote Ollama server and do not require Docker.
They exercise truth/lie controls, schema references, policy denial, path
containment, incomplete evidence, command failures and adapter tool conversion.
Read-only JSON/Markdown reports are generated from the ledger, not parsed from
model text.

## OpenSpec Workflow

The [project-claims specification](openspec/specs/project-claims/spec.md) defines
ClaimCheck's supported checks, permission boundaries, report contract, exit codes
and demo acceptance criteria.

The initial implementation change lives in
[openspec/changes/add-claimcheck](openspec/changes/add-claimcheck). Its proposal,
design, delta specification and completed tasks document the product's scope and
technical decisions.

```sh
make spec-status
make specs
OPENSPEC_TELEMETRY=0 openspec new change improve-claimcheck --schema spec-driven
# Write proposal/specs/design/tasks, implement and verify the approved change.
# When ready, archive with: openspec archive <change-name>
```

[openspec/config.yaml](openspec/config.yaml) contains concise project-wide context
and artifact-specific rules. The current change remains unarchived for review.

## Known Limitations

- This is bounded evidence gathering, not a proof that every sentence is true.
  Arbitrary prose, diagrams, remote README links and undocumented behavior are
  outside automatic coverage; model suggestions cannot establish truth.
- README checks use a minimal Python sandbox. Projects needing other runtimes,
  network installs, writable source or stateful shell setup need a separately
  reviewed execution strategy; ClaimCheck will not weaken isolation for them.
- Docker checks compare configuration, not image provenance, filesystem contents,
  runtime listening ports or Docker health. `EXPOSE` is metadata, not proof a
  service listens. Multi-stage builds, substitutions, continuations, shell-form
  CMD and advanced Dockerfile syntax require manual review.
- OpenAPI probes cover supplied GET/HEAD/OPTIONS examples, not all input values,
  authenticated flows or mutations. Required parameters without examples,
  referenced parameter/response objects, external references and non-JSON
  response schemas remain unverified. OpenAPI 3.0 nullable is normalized; this
  is not a complete OpenAPI conformance validator.
- Limits: 80 claims, 256 KiB per input/HTTP/model response, 16 KiB command output,
  20-second command timeout, 20 MiB/1000-file snapshots, 8 model calls and a
  180-second agent timeout. Tool operations have their own time limits.
- Model availability/tool-use quality varies. Model failure produces an explicit
  error and saves partial evidence; it does not silently fall back to fake output.
- Ollama is the only model backend. Other hosted-model providers are not supported;
  the native ADK adapter does not use LiteLLM.

## Security & Privacy Considerations

- No credentials, signing keys or certificates are embedded. `.env` and reports
  are ignored. TLS uses system trust verification and TLS 1.3 minimum; custom
  certificates must be verified before being added to the system trust store.
- README execution requires `--allow-exec`. The sandbox receives a read-only
  snapshot, excluding dotfiles, common credential/key/certificate files,
  symlinks, environments and dependency caches. The original source and Docker
  socket are not mounted. It runs non-root with no network, dropped capabilities,
  no new privileges, PID/CPU/memory limits and bounded temporary storage.
- Exclusion heuristics are **not a secret scanner**. Review source, output and
  model destinations before using `--agent`. Scripts and models can still
  encounter secrets placed in ordinary source files. Reports can contain
  command output; keep them private.
- APIs are probed only at the operator-approved base URL, without inherited proxy
  settings, auth credentials or redirected requests. Even GET may have side
  effects in a poorly designed API; use a test environment you own.
- Document text and tool output are untrusted. The model cannot authorize
  execution or manufacture ledger entries. Docker isolation is defense in depth,
  not a guarantee against hostile kernels/images; use a disposable VM for
  adversarial repositories.

## Future Improvements

- Broader README claim extraction with a human-reviewed execution plan.
- Additional reviewed runtime images and richer OpenAPI example coverage.
- Runtime image health/listening checks separate from configuration comparisons.

## License

Contributed under the repository's [MIT license](../../LICENSE).

## Purpose

Give maintainers repeatable evidence of gaps between documented project claims
and actual command execution, live API responses and built-image configuration,
with explicit capability approvals and no model-generated verdicts.

## ADDED Requirements

### Requirement: Bounded claim discovery
The system SHALL discover supported claims from root-level `README.md`,
`Dockerfile`, `openapi.yaml`, `openapi.yml` and `openapi.json`. It SHALL reject
inputs larger than 262144 bytes and audits with more than 80 discovered claims.
It SHALL NOT imply coverage of arbitrary prose, diagrams or undocumented behavior.

#### Scenario: Discover supported sources
- **WHEN** a project contains supported source files with executable claims
- **THEN** the system enumerates claims with source filenames and one-based line locations

#### Scenario: Missing or oversized input
- **WHEN** no supported claims exist, a document exceeds the size limit, or the claim count exceeds 80
- **THEN** the CLI reports an explicit error rather than a successful empty audit

### Requirement: Evidence-backed verdicts
The system SHALL associate each discovered claim with a stable ID, source
location and one of passed, failed, not_verified or error, using only tool evidence.
IDs SHALL be derived from claim kind, source, line and statement. Repeated
verification of an ID within one audit SHALL reuse its collected result.

#### Scenario: No check was executed
- **WHEN** a discovered claim has no collected observation
- **THEN** the report marks it not_verified, never passed

#### Scenario: Operational failure
- **WHEN** a requested check cannot run because its runtime or target is unavailable
- **THEN** the report records an error distinctly from observed drift

#### Scenario: Model attempts to invent evidence
- **WHEN** a caller requests verification or result recording for an unknown claim ID
- **THEN** the ledger rejects the ID and does not create a passed claim

#### Scenario: Repeat verification
- **WHEN** a known claim is verified more than once in one audit
- **THEN** the cached result is returned without repeating command execution or API probing

### Requirement: README command and output checks
The system SHALL discover non-comment command lines within `sh`, `bash`, `shell`
and `console` fences, removing a leading `$ ` prompt when present. Each supported
command SHALL execute independently without a shell. A following nonempty
`# expect:` annotation SHALL assert a case-sensitive stdout substring.

#### Scenario: Successful execution
- **WHEN** a supported command exits 0 and any expected stdout substring is present
- **THEN** the claim passes with argv, exit code, stdout, stderr and sandbox-image evidence

#### Scenario: Incorrect documented output
- **WHEN** a command exits 0 but its nonempty expected stdout substring is absent
- **THEN** the claim fails and the report retains the observed stdout

#### Scenario: Unsuccessful documented step
- **WHEN** a command exits nonzero without a timeout or sandbox exit code 125, 126 or 127
- **THEN** the claim fails with its captured execution evidence

#### Scenario: Runtime cannot execute the check
- **WHEN** command execution times out or returns sandbox exit code 125, 126 or 127
- **THEN** the claim is an error rather than an observed documentation failure

### Requirement: README local-link checks
The system SHALL check supported relative Markdown link targets outside fenced
blocks for existence, without requesting remote links or validating fragment
anchors. Resolved filesystem paths SHALL remain inside the selected project.

#### Scenario: Existing and missing targets
- **WHEN** a supported local link resolves inside the project
- **THEN** it passes if the target exists and fails if the target is missing

#### Scenario: Escaping target
- **WHEN** a link or symlink resolves outside the project
- **THEN** the check records an error without reading the external target

### Requirement: README execution safety
The system SHALL require operator approval and an isolated, bounded,
network-disabled Docker container to execute supported documented commands.

#### Scenario: Missing execution approval
- **WHEN** a README command is found without execution approval
- **THEN** the claim is not_verified and no command is executed

#### Scenario: False execution steps
- **WHEN** a command has an ordinary nonzero exit or lacks expected stdout, without a sandbox error or timeout
- **THEN** the claim fails with exit/output evidence

#### Scenario: Unsupported shell syntax
- **WHEN** a command requires shell operators or stateful setup
- **THEN** the claim remains not_verified

### Requirement: Bounded execution isolation
The system SHALL run approved commands non-root in a pinned, locally available
Docker image with no network, a read-only root and project snapshot, dropped
capabilities, no new privileges, and no Docker socket. Each command SHALL have
a 20-second timeout, 16384-byte output bounds, 64-PID limit, 256 MiB memory limit,
one CPU limit and a 16 MiB temporary filesystem.

#### Scenario: Snapshot excludes sensitive paths
- **WHEN** the sandbox snapshot is prepared
- **THEN** dotfiles, symlinks, common credential/key/certificate files and dependency caches are excluded
- **AND** the original project directory is not mounted into the command container

#### Scenario: Snapshot exceeds limits
- **WHEN** copied project content exceeds 20 MiB or 1000 files
- **THEN** execution fails explicitly rather than mounting the original project

#### Scenario: Timeout and cleanup
- **WHEN** execution completes or its client is terminated on timeout
- **THEN** the named temporary container is removed and cleanup errors are surfaced

### Requirement: Live OpenAPI checks
The system SHALL compare safe example requests against an operator-selected
live server using documented response status, media type and JSON schema.

#### Scenario: Schema drift and missing endpoint
- **WHEN** a response violates its JSON schema or a valid-example route returns 404
- **THEN** the tool records a failed claim with response/schema evidence

#### Scenario: Unapproved request capabilities
- **WHEN** an operation needs mutations, credentials or unresolved examples
- **THEN** no such request is automatically sent and the claim is not_verified

#### Scenario: Matching JSON response
- **WHEN** a GET example returns a documented non-error status, declared media type and schema-conforming JSON
- **THEN** the claim passes with method, path, status, content type and schema-error evidence

#### Scenario: Response mismatch
- **WHEN** a response has an undocumented status or media type, invalid JSON, or schema violations
- **THEN** the claim fails and schema evidence records locations and validators without retaining raw response bodies

#### Scenario: Documented error response to a valid example
- **WHEN** a valid-example probe returns HTTP 400 or higher even if the status is documented
- **THEN** the claim fails rather than treating the error response as proof of normal operation

#### Scenario: Status-only response
- **WHEN** a HEAD request or a response contract without content matches the returned non-error status
- **THEN** the claim passes for that documented response without claiming JSON-body validation

### Requirement: OpenAPI examples and reference boundaries
The system SHALL support OpenAPI 3.x documents, GET/HEAD/OPTIONS probes, explicit
path/query parameter examples and local JSON-schema references. It SHALL reject
YAML aliases, nesting beyond 64 levels and more than 10000 parsed nodes.
It SHALL NOT resolve external references or automatically perform TRACE or
mutating requests.

#### Scenario: Path and query examples
- **WHEN** required parameters have supported examples
- **THEN** path examples are URL-encoded and query examples are passed as query parameters

#### Scenario: Unsupported contract features
- **WHEN** an operation needs referenced parameters, referenced response objects, required header/cookie parameters, or lacks a supported JSON schema
- **THEN** the unsupported check remains not_verified rather than passed

#### Scenario: External reference
- **WHEN** the OpenAPI document includes an external reference
- **THEN** no external reference is retrieved and its operation checks remain not_verified

#### Scenario: Request or contract error
- **WHEN** a target is unreachable, response size exceeds the bound, or schema validation cannot execute
- **THEN** the affected check records an error rather than inventing an observation

### Requirement: Operator-selected network targets
The system SHALL take the API base URL from operator configuration rather than
OpenAPI `servers`. API and model URLs SHALL use HTTP(S), contain no URL
credentials, query or fragment, and require explicit approval for non-loopback
access and separate approval for non-loopback plaintext HTTP. HTTP clients SHALL
disable redirects and inherited proxy settings and verify HTTPS certificates
with a TLS 1.3 minimum.

#### Scenario: Remote API without approval
- **WHEN** a non-loopback API URL is selected without `--allow-remote-api`
- **THEN** the audit rejects the configuration before sending probes

#### Scenario: No API selected
- **WHEN** no API base URL is supplied
- **THEN** API claims remain not_verified and OpenAPI server declarations are not contacted

#### Scenario: Plaintext remote traffic
- **WHEN** a remote API or model uses HTTP without its separate plaintext approval
- **THEN** configuration validation rejects the request

#### Scenario: Redirected probe
- **WHEN** a selected API returns a redirect
- **THEN** the client records that response without following its destination

### Requirement: Docker configuration comparison
The system SHALL compare supported final Dockerfile settings with a selected
built image and retain the immutable image ID in evidence.

#### Scenario: Stale image
- **WHEN** declared port, environment or exec-form CMD differs from the built image
- **THEN** each supported mismatch is reported as failed

#### Scenario: Matching final image settings
- **WHEN** supported USER, WORKDIR, exec-form CMD/ENTRYPOINT, ENV or EXPOSE claims match the selected image
- **THEN** the corresponding claim passes with expected/actual values and the immutable image ID

#### Scenario: Accumulated environment and exposed ports
- **WHEN** the final stage repeats ENV or EXPOSE instructions
- **THEN** checks compare accumulated declared environment values and require all declared ports in image metadata
- **AND** unrelated image environment values are omitted from exported evidence

#### Scenario: Missing image selection
- **WHEN** no image is supplied
- **THEN** image claims remain not_verified without an automatic image pull, build or run

#### Scenario: Unsupported Dockerfile behavior
- **WHEN** a claim uses shell-form CMD, legacy ENV, build substitutions, continuations or multiple stages
- **THEN** the unsupported comparison remains not_verified
- **AND** metadata comparisons do not claim image provenance, listening ports or runtime health

#### Scenario: Image inspection failure
- **WHEN** the selected image cannot be inspected
- **THEN** affected image checks report an error rather than a Dockerfile mismatch

### Requirement: Native Ollama agent
The system SHALL use Google ADK and native Ollama tool calling without LiteLLM.
The model SHALL NOT have an API for writing verdicts or authorizing capabilities.
Its tool set SHALL be limited to `list_claims`, `verify_claim` and
`verify_all_claims`.

#### Scenario: Successful agent loop
- **WHEN** the model requests known verification tools
- **THEN** the tools gather evidence and the model provides separate advisory commentary

#### Scenario: Model failure or incomplete tool execution
- **WHEN** model access fails or the agent finishes before completing discovered checks
- **THEN** the CLI exits with an explicit error and saves partial evidence

#### Scenario: Bounded model execution
- **WHEN** an agent audit runs with default settings
- **THEN** it uses at most 8 model calls within a 180-second agent timeout
- **AND** document content or model output cannot expand file, command or network permissions

#### Scenario: No agent requested
- **WHEN** an audit runs without `--agent`
- **THEN** the same verification tools run deterministically without contacting a model

### Requirement: Structured reports and exit codes
The system SHALL write `report.json` and `report.md` to the selected output
directory. JSON schema version 1 SHALL include creation time, project, verdict
counts, discovered/executed claim counts, per-claim source/ID/observations/evidence
and optional agent commentary, tool names and token counts. Commentary SHALL
remain advisory and SHALL NOT replace tool-derived verdicts.

#### Scenario: Audit completion status
- **WHEN** an audit completes
- **THEN** it returns 2 if any check is an error, otherwise 1 if any claim failed, otherwise 3 if any claim is not_verified, otherwise 0

#### Scenario: Operational agent failure
- **WHEN** model access or the bounded agent loop fails
- **THEN** the CLI returns an explicit error and saves partial evidence with an agent-error annotation

### Requirement: Reproducible lying fixture
The project SHALL provide uv-locked setup, mise tool pins, a Makefile with setup,
doctor and demo targets, and OpenSpec artifacts.

#### Scenario: Full demo
- **WHEN** the full Docker demo runs successfully
- **THEN** it detects 8 planted lies, passes 5 positive controls and cleans temporary resources

#### Scenario: Lightweight demo
- **WHEN** Docker and model execution are omitted
- **THEN** the fixture reports exactly 2 passed, 3 failed, 8 not_verified and 0 error claims

#### Scenario: Exact full-demo acceptance
- **WHEN** the full Docker demo runs
- **THEN** it returns 0 only for exactly 5 passed, 8 failed, 0 not_verified and 0 error claims
- **AND** it stops its ephemeral loopback server and removes its temporary image and command containers

#### Scenario: Planted gaps and controls
- **WHEN** the full fixture is checked
- **THEN** failures cover missing README command input, wrong documented stdout, a broken local link, image ENV/EXPOSE/CMD drift, a wrong API field type and a missing API route
- **AND** positive controls cover a successful command, an existing link, image USER/WORKDIR and the health API

### Requirement: Developer workflow
The system SHALL provide locked setup, prerequisite diagnostics, deterministic
quality checks, package builds and OpenSpec validation through Make targets.
The development container SHALL bind-mount host source rather than store source
only in its writable container filesystem.

#### Scenario: Setup preserves local configuration
- **WHEN** `make setup` runs with an existing local `.env`
- **THEN** dependencies are synchronized from the lockfile without overwriting that configuration

#### Scenario: Doctor diagnostics
- **WHEN** `make doctor` runs
- **THEN** it reports tools, Docker daemon and sandbox-image readiness without installing prerequisites
- **AND** model availability is checked only when model diagnostics are requested

#### Scenario: Installable demonstration
- **WHEN** a wheel is built and installed independently of the source checkout
- **THEN** it includes the synthetic fixture needed to run the lightweight demo

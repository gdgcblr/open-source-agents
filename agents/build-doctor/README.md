# BuildDoctor

> An evidence-based build, test, runtime, and API diagnosis agent for projects in any language or ecosystem.

## Overview

### Problem Statement & Intended Users

Developers spend significant time interpreting long failure logs, separating symptoms from root causes, and deciding what to try next. BuildDoctor turns supplied evidence into ranked hypotheses, safe next steps, and explicit verification status.

It is intended for developers, students, open-source contributors, and small teams working with any language, build system, framework, or API.

### Why BuildDoctor Exists Alongside Coding Agents

Coding agents are optimized to edit code and execute tasks. BuildDoctor is an independent evidence-first investigator: it turns a failure into a reviewable diagnosis before a coding agent changes the project, then checks a developer-supplied result without claiming success prematurely.

Its differentiators are evidence-linked hypotheses, language and API neutrality, a read-only safety boundary, repeatable structured reports, and native MCP interoperability.

### Target User Workflow

1. Run the normal build, test, or API check and save the relevant output.
2. Connect the companion MCP server to an MCP-compatible client, or use the ADK agent directly.
3. Submit the failure output and project path for diagnosis.
4. Review the evidence, ranked root causes, missing evidence, and remediation plan.
5. Apply a change manually or with a separate coding agent.
6. Submit the original and new results to the MCP `verify_resolution` tool; BuildDoctor marks the issue verified only when deterministic before/after evidence supports that conclusion.

This makes BuildDoctor a diagnostic gate and verification companion, not another autonomous code editor.

### Key Features

- Classifies common compilation, dependency, test, runtime, and API failure signals.
- Covers configuration, permissions, network/TLS, resource, data/schema, CI/container, and concurrency/state signals as well.
- Extracts evidence from logs instead of treating an unverified guess as fact.
- Inspects common project manifests including Maven, Gradle, npm, Python, Go, Rust, PHP, and Elixir projects.
- Produces ordered, read-only remediation steps.
- Clearly reports when verification is pending.
- Exposes the same workflow as deterministic Java code and a Google ADK tool-enabled agent.

## Technical Stack

- **Language & Runtime:** Java 17+ for this implementation
- **Build Tool:** Maven 3.9+
- **Agent Framework:** Google Agent Development Kit for Java 1.12.0
- **Model:** Gemini, configured through `GEMINI_API_KEY`
- **Supported Evidence:** Logs and project manifests from any language or runtime

## Architecture & Data Flow

The ADK root agent receives failure output and project context, calls two read-only tools, and returns a structured diagnostic report. The tools do not execute commands or change project files.

```text
[Failure log + project path] -> [BuildDoctor ADK agent]
                                      |
                    +-----------------+-----------------+
                    |                                   |
             [Log analysis]                    [Manifest inspection]
                    |                                   |
                    +----------> [Evidence report]
```

## Prerequisites

- Java 17 or newer
- Maven 3.9 or newer
- A Gemini API key only for the optional ADK model-driven flow

The deterministic analyzer does not require an API key. The project uses standard Java and Maven commands and does not depend on OS-specific shell tools. Java and Maven installation methods are platform-specific, but the source code and commands are portable across macOS, Linux, and Windows.

## Installation & Setup

From the repository root:

```bash
cd agents/build-doctor
mvn test
```

On Windows PowerShell, use the same command from this directory. If Maven is not installed, install Maven 3.9+ using the official Apache Maven instructions or run the deterministic analyzer from an environment that already provides Maven.

On macOS and Linux, use `java` and `mvn` from a terminal. On Windows PowerShell or Command Prompt, use the same `java` and `mvn` commands after adding the JDK and Maven `bin` directories to `PATH`. The optional MCP connection uses the Python executable path appropriate to the platform: `.venv/bin/python` on macOS/Linux or `.venv\\Scripts\\python.exe` on Windows.

The `.env.example` file documents configuration. Java does not automatically load `.env` files, so set variables in your shell instead. Never commit a real `.env` file or API key.

## Configuration & Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | Only for ADK | Gemini API key used by the model-driven agent |
| `MODEL_NAME` | No | Gemini model name; defaults to `gemini-2.5-flash` |

The default model is used only to explain deterministic tool results. If your ADK model provider exposes Gemma 3 4B, you can set `MODEL_NAME=gemma-3-4b-it` for a smaller explanation model. Model availability and authentication depend on the provider; the deterministic diagnosis and verification rules do not.

## How to Run

Build the project:

```bash
mvn package -DskipTests
```

Run the deterministic analyzer against a saved failure log and the target project directory:

```bash
java -cp target/classes community.opensource.ai.builddoctor.BuildDoctorCli /path/to/failure.log /path/to/project
```

For scripts and coding agents, request the stable JSON contract:

```bash
java -cp target/classes community.opensource.ai.builddoctor.BuildDoctorCli --json /path/to/failure.log /path/to/project
```

The first argument can contain build, test, runtime, or API output from any ecosystem. The second argument is optional project context; when provided, BuildDoctor reads only recognized manifest files.

The ADK entry point is `BuildDoctorAgent.create()`. An ADK-compatible runner or development UI can load this root agent and expose its read-only local tools. To use the companion MCP server instead, call `BuildDoctorAgent.createWithMcp("/absolute/path/to/.venv/bin/python")`; ADK launches `python -m build_doctor_mcp.server` over stdio. Configure `GEMINI_API_KEY` only for the model-driven path.

The MCP path is tested independently over real stdio initialization, tool discovery, and `analyze_failure` invocation. The Java factory itself is not a standalone process; an ADK runner or application must own the agent lifecycle and call `close()` so the MCP toolset is released.

For a no-model connection check, run `BuildDoctorApplication` with `BUILD_DOCTOR_PYTHON` pointing to the Python environment that has `build-doctor-mcp` installed. It starts the MCP child process, discovers the tools, prints their names, and closes the agent without sending a Gemini request.

## Example Input & Output

### Example Input

```text
error: module not found: payments.client
Tests run: 12, Failures: 1, Errors: 0, Skipped: 0
```

### Example Output

```text
Failure type: dependency-resolution
Summary: The build could not resolve or download one or more dependencies.
Confidence: high
Evidence:
- error: module not found: payments.client
Next steps:
- Inspect the dependency name, version, lockfile, and configured registries.
- Check repository access and whether the requested version exists.
Verification: pending: no verification run was supplied
```

The analyzer reports what deterministic rules and evidence support. One signal establishes an observed failure, not a root cause. A suggested fix remains unconfirmed until a new result is supplied and verified. The language model, including optional Gemma 3 4B, may summarize this result but cannot override it.

## How to Test

```bash
mvn test
```

The tests cover compilation, dependency, test, and unknown failure signatures, common non-Java manifest inspection, ADK agent construction, and tool registration.

The opt-in cross-language discovery test requires `BUILD_DOCTOR_PYTHON` and `BUILD_DOCTOR_MCP_PYTHONPATH`; it starts the real Python server over stdio and verifies discovery and cleanup.

## Known Limitations

- The first version uses robust failure signatures rather than deeply parsing every ecosystem's native report format.
- The analyzer does not rerun builds or tests; verification remains pending until a separate result is supplied.
- The ADK path requires a configured Gemini model and an ADK-compatible runner or development UI.
- Logs and manifests can contain secrets or personal data; review them before sending them to a hosted model.
- The MCP bridge requires the companion server to be installed in the configured Python environment.

## Completed MVP Milestones

- Deterministic evidence scoring with confidence limits.
- Structured test-report evidence through the companion MCP server.
- Before/after verification without command execution.
- Cross-platform MCP client presets.
- Public cross-ecosystem evaluation cases.

## Security & Privacy Considerations

- API keys are loaded from environment variables and are never stored in source control.
- The selected project path is inspected read-only. No shell commands are executed.
- The agent does not edit files, install dependencies, delete data, commit code, or push changes.
- Suggested changes are hypotheses, not automatic fixes; verification is `pending` until a new result is supplied.
- Treat diagnostic logs as potentially sensitive input and provide only the files needed for diagnosis.

## Future Improvements

- Add structured parsers for Surefire, JUnit, pytest, npm, Gradle, and GitHub Actions reports.
- Add post-fix verification input and before/after comparison.
- Add evaluation fixtures for each supported ecosystem.
- Expose the same read-only operations through the companion MCP server.

## License

This project is contributed under the repository's MIT License.

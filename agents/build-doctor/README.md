# BuildDoctor

> An evidence-based build, test, runtime, and API diagnosis agent for projects in any language or ecosystem.

## Overview

### Problem Statement & Intended Users

Developers spend significant time interpreting long failure logs, separating symptoms from root causes, and deciding what to try next. BuildDoctor turns supplied evidence into ranked hypotheses, safe next steps, and explicit verification status.

It is intended for developers, students, open-source contributors, and small teams working with any language, build system, framework, or API.

### Key Features

- Classifies common compilation, dependency, test, runtime, and API failure signals.
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

The deterministic analyzer does not require an API key. The project uses standard Java and Maven commands and does not depend on OS-specific shell tools.

## Installation & Setup

From the repository root:

```bash
cd agents/build-doctor
mvn test
```

On Windows PowerShell, use the same command from this directory. If Maven is not installed, install Maven 3.9+ using the official Apache Maven instructions or run the deterministic analyzer from an environment that already provides Maven.

The `.env.example` file documents configuration. Java does not automatically load `.env` files, so set variables in your shell instead. Never commit a real `.env` file or API key.

## Configuration & Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | Only for ADK | Gemini API key used by the model-driven agent |
| `MODEL_NAME` | No | Gemini model name; defaults to `gemini-2.5-flash` |

## How to Run

Build the project:

```bash
mvn package -DskipTests
```

Run the deterministic analyzer against a saved failure log and the target project directory:

```bash
java -cp target/classes community.opensource.ai.builddoctor.BuildDoctorCli /path/to/failure.log /path/to/project
```

The first argument can contain build, test, runtime, or API output from any ecosystem. The second argument is optional project context; when provided, BuildDoctor reads only recognized manifest files.

The ADK entry point is `BuildDoctorAgent.create()`. An ADK-compatible runner or development UI can load this root agent and expose its read-only tools. Configure `GEMINI_API_KEY` only for that model-driven path.

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

The analyzer reports what the evidence supports. It does not claim that a suggested fix worked until a new build or test result is supplied.

## How to Test

```bash
mvn test
```

The tests cover compilation, dependency, test, and unknown failure signatures, common non-Java manifest inspection, ADK agent construction, and tool registration.

## Known Limitations

- The first version uses robust failure signatures rather than deeply parsing every ecosystem's native report format.
- The analyzer does not rerun builds or tests; verification remains pending until a separate result is supplied.
- The ADK path requires a configured Gemini model and an ADK-compatible runner or development UI.
- Logs and manifests can contain secrets or personal data; review them before sending them to a hosted model.

## Security & Privacy Considerations

- API keys are loaded from environment variables and are never stored in source control.
- The selected project path is inspected read-only. No shell commands are executed.
- The agent does not edit files, install dependencies, delete data, commit code, or push changes.
- Treat diagnostic logs as potentially sensitive input and provide only the files needed for diagnosis.

## Future Improvements

- Add structured parsers for Surefire, JUnit, pytest, npm, Gradle, and GitHub Actions reports.
- Add post-fix verification input and before/after comparison.
- Add evaluation fixtures for each supported ecosystem.
- Expose the same read-only operations through the companion MCP server.

## License

This project is contributed under the repository's MIT License.

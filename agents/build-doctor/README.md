# BuildDoctor

> An evidence-based Java build and test diagnosis agent that turns Maven failures into ranked hypotheses, safe next steps, and honest verification status.

## Overview

### Problem Statement & Intended Users

Developers often spend significant time interpreting long Maven logs, distinguishing symptoms from root causes, and deciding what to try next. BuildDoctor is intended for Java developers, students, open-source contributors, and small teams who need a structured starting point when a Maven build or test fails.

### Key Features

- Classifies supported compilation, dependency-resolution, and test failures.
- Links the diagnosis to extracted log evidence and selected project evidence.
- Produces ordered, read-only remediation steps and explicitly reports when verification is still pending.
- Exposes the same workflow as deterministic Java code and as a Google ADK tool-enabled agent.

## Technical Stack

- **Language & Runtime:** Java 17+
- **Build Tool:** Maven
- **Agent Framework:** Google Agent Development Kit for Java 1.12.0
- **Model:** Gemini, configured through `GEMINI_API_KEY`

## Architecture & Data Flow

The ADK root agent receives a failure description, calls `analyzeBuildLog` and `inspectProject`, and turns their factual output into a structured diagnostic report. The tools are read-only: they inspect supplied text and a selected `pom.xml`, but do not execute commands or change project files.

```text
[Maven log + project path] -> [ADK BuildDoctor agent]
				      |
		   +----------------+----------------+
		   |                                 |
	   [Log analysis tool]              [Project inspection tool]
		   |                                 |
		   +----------> [Evidence-based report]
```

## Prerequisites

- Java 17 or newer
- Maven 3.9 or newer
- A Gemini API key from Google AI Studio for the ADK flow

## Installation & Setup

```bash
cd agents/build-doctor
mvn test
```

For the model-driven ADK flow, set `GEMINI_API_KEY` in your environment. The real `.env` file must never be committed. The deterministic CLI does not require an API key.

## Configuration & Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | Only for ADK | Gemini API key used by ADK |
| `MODEL_NAME` | No | Gemini model name; defaults to `gemini-2.5-flash` |

## How to Run

Run the deterministic diagnostic path against a saved Maven output file:

```bash
mvn package -DskipTests
java -cp target/classes community.opensource.ai.builddoctor.BuildDoctorCli /path/to/maven.log /path/to/java-project
```

The ADK entry point is `BuildDoctorAgent.create()`. It can be loaded by an ADK-compatible runner or development UI and uses the same read-only tools as the CLI.

## Example Input & Output

### Example Input

```text
[ERROR] COMPILATION ERROR
[ERROR] cannot find symbol
```

### Example Output

```text
Failure type: compilation
Summary: The build contains a Java compilation failure.
Confidence: high
Evidence:
- [ERROR] COMPILATION ERROR
- [ERROR] cannot find symbol
Next steps:
- Inspect the first compiler error and its source location.
Verification: pending: no verification run was supplied
```

## How to Test

```bash
mvn test
```

The tests cover compilation, dependency-resolution, test, and unknown failure signatures, plus ADK agent construction and tool registration.

## Known Limitations

- The first version supports common Maven failure signatures rather than every possible build failure.
- The deterministic analyzer does not rerun Maven; verification remains pending until a separate result is supplied.
- The ADK path requires a configured Gemini model and an ADK runner or development UI.

## Security & Privacy Considerations

- API keys are loaded from environment variables and are never stored in source control.
- The project root is supplied explicitly and only `pom.xml` is inspected by the current project tool.
- The agent does not edit files, install dependencies, execute shell commands, delete data, commit code, or push changes.
- Logs and project configuration may contain sensitive information; review data before sending it to a hosted model.

## Future Improvements

- Add structured Surefire report inspection.
- Add post-fix verification input and before/after comparison.
- Add more Maven failure fixtures and evaluation cases.

## License

This project is contributed under the repository's MIT License.

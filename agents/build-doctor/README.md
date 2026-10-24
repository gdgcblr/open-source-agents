# ADK Java Agent

> A Google Agent Development Kit (ADK) for Java project solving a practical problem for developers or teams.

## Overview

### Problem Statement & Intended Users

_To be completed after the project use case is confirmed._

### Key Features

_To be completed after the project use case is confirmed._

## Technical Stack

- **Language & Runtime:** Java 17+
- **Build Tool:** Maven
- **Agent Framework:** Google Agent Development Kit for Java
- **Model:** Gemini, configured through `GEMINI_API_KEY`

## Architecture & Data Flow

The ADK root agent receives a user request, calls narrowly scoped tools where needed, and returns a documented result. Tool access and data boundaries will be defined by the selected use case.

## Prerequisites

- Java 17 or newer
- Maven 3.9 or newer
- A Gemini API key from Google AI Studio

## Installation & Setup

```bash
cd agents/adk-java-agent
cp .env.example .env
mvn test
```

Set `GEMINI_API_KEY` in your environment before running the agent. The real `.env` file must never be committed.

## Configuration & Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | Gemini API key used by ADK |
| `MODEL_NAME` | No | Gemini model name; defaults to `gemini-2.5-flash` |

## How to Run

_To be completed with the confirmed use case and demo command._

## Example Input & Output

_To be completed with a genuine example after implementation._

## How to Test

```bash
mvn test
```

## Known Limitations

- The first version will target a focused demo workflow.
- The agent will require access to the configured Gemini model.

## Security & Privacy Considerations

- API keys are loaded from environment variables and are never stored in source control.
- The agent will only access data explicitly required by the selected use case.
- Any tool capable of changing external state will require explicit user confirmation.

## Future Improvements

- Add additional tools after the core workflow is tested.
- Add evaluation cases for common and edge-case inputs.

## License

This project is contributed under the repository's MIT License.

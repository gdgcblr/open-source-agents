\# AGENTS.md — Android Dev Assistant



\## Project Overview

Android Dev Assistant is an AI-powered Android troubleshooting agent built using Google Agent Development Kit (ADK), Gemini and a local JSON knowledge base.



Its purpose is to help Android developers understand common development errors and find practical solutions.



\## Technology Stack

\- Python

\- Google ADK

\- Gemini API

\- JSON knowledge base

\- Android development knowledge: Kotlin, Java, Gradle, Jetpack Compose and Firebase



\## Project Structure

\- `agent.py` — Defines the root ADK agent.

\- `android\_tools.py` — Contains the Android troubleshooting search tool.

\- `knowledge/android\_errors.json` — Stores troubleshooting knowledge.

\- `test\_android\_tools.py` — Tests the troubleshooting tool.

\- `requirements.txt` — Python dependencies.

\- `.env.example` — Example environment configuration.



\## Development Guidelines

1\. Keep the agent focused on Android development troubleshooting.

2\. Prefer simple, modular and reusable Python code.

3\. Keep troubleshooting information in the JSON knowledge base.

4\. Validate user input before processing it.

5\. Do not execute user-provided code or shell commands.

6\. Do not expose API keys, credentials or other secrets.

7\. Do not invent documentation links or troubleshooting steps.

8\. Clearly distinguish likely causes from confirmed causes.

9\. Keep responses beginner-friendly and actionable.



\## Testing

Before submitting changes:

1\. Run `python -m pytest` if pytest is configured.

2\. Run `python test\_android\_tools.py`.

3\. Verify that the agent can load successfully.

4\. Test known Android errors and unknown errors.



\## Security

\- Never commit `.env` or API keys.

\- Use `.env.example` for placeholder configuration only.

\- Treat error logs and user-provided code as untrusted input.

\- Never perform destructive project changes without explicit approval.



\## Contribution Expectations

\- Keep changes focused and easy to review.

\- Update the README when project functionality changes.

\- Add tests for new troubleshooting functionality.

\- Follow the parent repository's contribution guidelines.




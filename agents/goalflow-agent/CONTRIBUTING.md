# Contributing to GoalFlow

Thank you for your interest in contributing to GoalFlow! This project is built as an open-source AI agent demonstration using Python and Google's Agent Development Kit (ADK).

## Development Setup

1. Ensure Python 3.11+ is installed.
2. Clone the repository and set up a virtual environment:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -e . --no-build-isolation
   ```
3. Copy `.env.example` to `.env` and configure your API key (optional for unit tests):
   ```bash
   cp .env.example .env
   ```

## Code Guidelines

- **Architecture Boundary**: Maintain clear separation between deterministic business logic (in `db.py`, `progress.py`) and generative intelligence (in `agent.py`).
- **Safe Tools**: Never grant the language model raw SQL execution privileges. Always wrap database mutations in validated Python functions in `tools.py`.
- **Anti-Hallucination Guardrails**: Always enforce that achievements and statistics cited to users come from stored records.
- **Type Annotations & Docstrings**: Ensure all tool functions and database operations include complete Python type hints and clear docstrings.

## Testing Guidelines

- Always run the test suite before submitting pull requests:
  ```bash
  pytest -v
  ```
- All unit tests must run without requiring live network calls or paid API credits (use in-memory SQLite and mock fixtures).
- New features must include corresponding test cases in `tests/`.

## Pull Request Process

1. Fork the repository and create your feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Commit your changes with descriptive commit messages.
3. Verify that all 21+ tests pass.
4. Submit your pull request with a summary of changes and test evidence.

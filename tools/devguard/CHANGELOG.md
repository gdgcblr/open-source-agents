# Changelog

All notable changes to DevGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Ollama provider** (`OllamaProvider`) — fully local AI inference via the Ollama REST API using Python stdlib only (no extra pip packages). Supports any model pulled with `ollama pull`.
- `create_provider()` factory function in `ai_provider.py` — selects Gemini or Ollama based on `--provider` flag, `DEVGUARD_AI_PROVIDER` env var, or auto-detection from existing env vars.
- `--provider` CLI option on `commit-message`, `diagnose`, and `pr-description` commands (`gemini` | `ollama`).
- `DEVGUARD_AI_PROVIDER`, `OLLAMA_BASE_URL`, and `OLLAMA_MODEL` environment variables documented in `.env.example`.
- Provider name reflected in output labels (e.g. `[AI-Assisted (ollama)]` instead of hardcoded `[AI-Assisted (gemini)]`).
- Helpful model-not-found error that lists locally available Ollama models.

## [0.1.0] - 2026-10-24

### Added
- Initial release of DevGuard CLI.
- `devguard run` — policy-governed command execution with interactive approval.
- `devguard init` — configuration file bootstrapper with preset support.
- `devguard policy explain` — policy decision explainer with specificity scoring.
- `devguard history` — structured JSONL audit log viewer with secret redaction.
- `devguard preset list / show` — built-in policy presets (`conservative`, `development`, `custom`).
- `devguard commit-message` — AI-assisted conventional commit message generator with deterministic fallback.
- `devguard diagnose` — supervised command execution with structured failure diagnosis.
- `devguard pr-description` — Markdown PR description generator from git branch context.
- `python -m devguard` entry point (`__main__.py`).
- PEP 561 `py.typed` marker for typed package consumers.
- PyPI-ready `pyproject.toml` with classifiers, URLs, and optional extras (`[ai]`, `[all]`, `[dev]`).

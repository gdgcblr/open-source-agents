# AI Developer Tools & Utilities (`tools/`)

This directory houses reusable developer tools, Model Context Protocol (MCP) servers, evaluation harnesses, and utility libraries built to support AI agents and AI-assisted workflows.

## What Belongs Here

Submissions in `tools/` represent reusable components and utilities rather than standalone end-to-end agents. Examples include:

- **MCP Servers & Integrations**: Model Context Protocol servers connecting models to databases, local filesystems, SaaS APIs, or developer environments.
- **Evaluation & Benchmarking Tools**: Harnesses to test agent outputs, measure latency/cost, detect hallucinations, or validate tool calling.
- **Prompt Engineering & Management Utilities**: Prompt formatters, template linters, or dynamic context builders.
- **AI Automation & Developer Utilities**: Git hooks, CI helpers, synthetic test data generators, token usage calculators, and CLI utilities.
- **API Adapters & Connectors**: Standardized wrappers bridging agent frameworks to external protocols or services.

## Directory Standards

Every tool contribution must be completely self-contained within its own dedicated directory:

```
tools/<project-slug>/
├── README.md               # Copied and completed from template/README.md
├── .env.example            # Example configuration with placeholder values
├── .gitignore              # Local ignores for dependencies and secrets
├── requirements.txt        # (or package.json, Cargo.toml, etc.)
└── <source_files>          # Tool implementation code
```

### Naming Conventions
- Directory names must be **lowercase kebab-case** (e.g., `mcp-document-search`, `prompt-evaluator`, `token-cost-tracker`).
- Choose a descriptive name reflecting the tool's actual function.
- Do not use generic names like `my-tool`, `final-test`, or `helper`.
- Directory names must be unique within `tools/`. Before naming your directory, check existing folders.

## How to Contribute a Tool

1. Read the full contribution guide in [CONTRIBUTING.md](../CONTRIBUTING.md).
2. Create your directory: `tools/<project-slug>/`.
3. Copy `template/README.md`, `template/.gitignore`, and `template/.env.example` into your project directory.
4. Implement your tool using whatever language and framework is best suited for your use case (e.g., Python, TypeScript, Go, Rust, or shell).
5. Document prerequisites, installation, environment setup, sample invocation/usage, and testing instructions.
6. Verify locally that the setup instructions work cleanly from scratch and that no credentials or dependencies are committed.
7. Submit a Pull Request following the [PULL_REQUEST_TEMPLATE](../.github/PULL_REQUEST_TEMPLATE.md).

---

## Directory Index

| Tool Directory | Description | Category / Protocol | Contributor |
| :--- | :--- | :--- | :--- |
| [`model-aware-prompt-enhancer`](model-aware-prompt-enhancer/README.md) | Diagnoses prompts, asks for missing details instead of guessing, applies minimal intent-preserving patches, and measures the result with A/B tests (Claude, GPT, Gemini profiles) | Prompt engineering / CLI, Claude Code plugin, MCP server | [@bhargavi905](https://github.com/bhargavi905) |

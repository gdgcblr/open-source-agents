# AI Agents (`agents/`)

This directory houses community-contributed AI agents, multi-agent systems, and task-oriented assistants.

## What Belongs Here

Submissions in `agents/` typically represent end-to-end agents or agentic workflows designed to perform tasks autonomously or semi-autonomously. Examples include:

- **Autonomous Task Agents**: Coding assistants, research synthesizers, data extractors, meeting assistants.
- **Multi-Agent Systems**: Collaborative agent groups (e.g., researcher + writer + reviewer pipelines).
- **Conversational & Interactive Agents**: Domain-specific chat agents with tool-calling capabilities.
- **Workflow & Planning Agents**: Agents that break down goals into sub-actions and execute them against external environments.

## Directory Standards

Every agent contribution must be completely self-contained within its own dedicated directory:

```
agents/<project-slug>/
├── README.md               # Copied and completed from template/README.md
├── .env.example            # Example configuration with placeholder values
├── .gitignore              # Local ignores for dependencies and secrets
├── requirements.txt        # (or package.json, pyproject.toml, etc.)
└── <source_files>          # Agent implementation code
```

### Naming Conventions
- Directory names must be **lowercase kebab-case** (e.g., `research-assistant`, `git-commit-helper`, `cloud-cost-agent`).
- Choose a descriptive name reflecting the agent's actual function.
- Do not use generic names like `my-agent`, `final-project`, or `test`.
- Directory names must be unique within `agents/`. Before naming your directory, check existing folders.

## How to Contribute an Agent

1. Read the full contribution guide in [CONTRIBUTING.md](../CONTRIBUTING.md).
2. Create your directory: `agents/<project-slug>/`.
3. Copy `template/README.md`, `template/.gitignore`, and `template/.env.example` into your project directory.
4. Implement your agent using whatever language and framework is best suited for your use case (e.g., Google ADK, LangGraph, CrewAI, OpenAI Agents SDK, or custom scripts).
5. Document prerequisites, installation, environment setup, example inputs/outputs, and testing instructions.
6. Verify locally that the setup instructions work cleanly from scratch and that no credentials or virtual environments are tracked.
7. Submit a Pull Request following the [PULL_REQUEST_TEMPLATE](../.github/PULL_REQUEST_TEMPLATE.md).

---

## Directory Index

| Agent Directory | Description | Framework / Stack | Contributor |
| :--- | :--- | :--- | :--- |
| [`resume-jd-match-agent`](resume-jd-match-agent/) | Compares a resume (PDF or text) with a job description and returns an ATS-style match report with score, missing skills and bullet rewrites | Google ADK + Gemini | Abhinav Maharana |

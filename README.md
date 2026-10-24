# open-source-ai

> **Build it. Document it. Open-source it.**

A community-driven collection of practical, documented, and open-source AI agents and developer tools, built with diverse frameworks and technologies.

---

## Introduction

As AI systems evolve from single prompt-response interactions to multi-step reasoning, tool-using agents, and specialized developer utilities, the need for transparent, reproducible, and practical open-source implementations has never been greater.

`open-source-ai` is a collaborative monorepo curated to showcase working, well-documented AI projects. The goal is to provide developers, researchers, and builders with a shared catalog of real-world patterns—ranging from autonomous task agents to Model Context Protocol (MCP) servers and evaluation harnesses.

This repository is designed to be accessible, framework-agnostic, and easy to navigate whether you are looking for reference implementations or contributing your own creation.

---

## Acceptable Project Categories

We welcome practical, working AI contributions across a variety of categories. These categories are illustrative rather than rigid constraints:

- **AI Agents**: Autonomous, semi-autonomous, or task-oriented agents, conversational assistants, and multi-agent coordination systems.
- **Model Context Protocol (MCP) Servers & Integrations**: Servers providing structured context, tools, and prompts to models from databases, filesystems, developer tools, or web services.
- **AI Developer Utilities**: Command-line interfaces, prompt helpers, token trackers, context formatters, and workflow automations.
- **AI-Powered Workflows & Automation**: Specialized pipelines for code generation, documentation review, PR triage, research synthesis, or data transformation.
- **Evaluation, Testing & Safety Utilities**: Tools and harnesses to measure model accuracy, benchmark latency and cost, detect hallucinations, or test tool calls.
- **Other Practical AI Tooling**: Reusable libraries, adapters, and connectors that help developers build AI applications.

---

## Technology Flexibility

This repository is **completely framework-agnostic and language-neutral**. Contributors are encouraged to select the stack best suited to their problem domain.

Accepted technologies and ecosystems include, but are not limited to:
- **Google Agent Development Kit (ADK)**
- **OpenAI Agents SDK**
- **LangGraph & LangChain**
- **CrewAI**
- **Model Context Protocol (MCP)**
- **Python or TypeScript / JavaScript AI runtimes**
- **Go, Rust, or other systems languages**
- **Local / open-weights model runtimes** (e.g., Ollama, vLLM, llama.cpp)
- **Hosted model APIs** (e.g., Gemini, OpenAI, Anthropic, Mistral)

No single cloud provider, framework, or model vendor is mandated.

---

## Repository Structure

The repository is organized into distinct directories to keep projects isolated, modular, and easy to maintain:

```
open-source-ai/
├── README.md               # Repository overview, philosophy, and index
├── CONTRIBUTING.md         # Detailed 12-step contributor guide and standards
├── .gitignore              # Repository-wide ignores for secrets, virtual environments, and caches
├── agents/                 # Directory for autonomous and task-oriented agents
│   └── README.md           # Guidelines and index of agent projects
├── tools/                  # Directory for developer tools, MCP servers, and utilities
│   └── README.md           # Guidelines and index of tooling projects
├── template/               # Starter files for new contributions
│   ├── README.md           # Reusable project documentation template
│   ├── .gitignore          # Recommended per-project .gitignore
│   └── .env.example        # Sanitized environment variable template
└── .github/
    └── PULL_REQUEST_TEMPLATE.md  # Standard checklist for submitting pull requests
```

- **[`agents/`](agents/README.md)**: Contains end-to-end agents and multi-agent workflows. Each agent lives in its own dedicated subfolder (`agents/<project-slug>/`).
- **[`tools/`](tools/README.md)**: Contains developer utilities, MCP servers, evaluation harnesses, and reusable components. Each tool lives in its own dedicated subfolder (`tools/<project-slug>/`).
- **[`template/`](template/README.md)**: Provides a standardized documentation blueprint, environment template, and local `.gitignore` so contributors can document their work consistently.

---

## 🌟 Featured Projects

- **[`agents/namma-traffic-agent/`](agents/namma-traffic-agent/)** — **Namma Travel**: Real-time multimodal Bengaluru transit copilot with live metro, BMTC buses, and cab fare saver. Includes mobile app package in [`namma-travel-app/`](namma-travel-app/) (Android & iPhone) and executive Word presentation (`.docx`).

---

## Quick Start for Contributors

Ready to contribute? Follow this straightforward fork-and-pull-request workflow:

1. **Browse existing contributions**: Check [`agents/`](agents/README.md) and [`tools/`](tools/README.md) to explore existing work and choose a unique, descriptive project name.
2. **Fork the repository**: Fork this repository to your personal GitHub account.
3. **Clone your fork**:
   ```bash
   git clone https://github.com/<your-username>/<repo-name>.git
   cd <repo-name>
   ```
4. **Create a branch**:
   ```bash
   git checkout -b feat/<your-project-slug>
   ```
5. **Add your project**: Create a dedicated directory under `agents/<project-slug>/` or `tools/<project-slug>/`. Copy `template/README.md`, `template/.gitignore`, and `template/.env.example` into your folder.
6. **Implement and document**: Write your code, declare dependencies in a manifest (`requirements.txt`, `package.json`, etc.), and document setup, usage, and examples in your project's `README.md`.
7. **Test thoroughly**: Verify that installation and execution work on a clean environment and that no credentials or virtual environments are tracked.
8. **Commit and push**:
   ```bash
   git add agents/<project-slug>/   # or tools/<project-slug>/
   git commit -m "feat(agents): add <project-slug>"
   git push -u origin feat/<your-project-slug>
   ```
9. **Open a Pull Request**: Submit your PR against the upstream `main` branch, completing the [Pull Request Checklist](.github/PULL_REQUEST_TEMPLATE.md).

For step-by-step guidance and detailed Git commands, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Contribution Standards

To maintain technical credibility and long-term utility, all contributions are reviewed against four core criteria:

1. **Reproducibility**: Clear prerequisites, dependency specifications, and setup instructions that work out-of-the-box.
2. **Documentation Quality**: Comprehensive documentation using the provided template, including realistic inputs/outputs and known limitations.
3. **Security & Privacy**: Zero committed credentials, API keys, or private data. All configuration must use environment variables or sanitized configuration files.
4. **Focused Scope**: Each contribution is isolated in its own directory and does not alter unrelated parts of the repository.

---

## Community Context

This repository was established in collaboration with **GDG Cloud Bengaluru** as part of the **FORK. BUILD. MERGE.** initiative under **Road to DevFest 2026**.

While seeded during this community event, this repository is designed as an enduring, public open-source catalog. Contributions, maintenance, and community participation continue beyond the event.

---

## License

This project is licensed under the [MIT License](LICENSE) &copy; 2026 GDG Cloud Bengaluru Community.

